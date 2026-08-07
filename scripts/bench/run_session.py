"""Headless benchmark runner: feed audio clips through the real Voxis translator
and capture the translation text, the model's source transcription, and the
onset->first-audio latency — then score.py turns those into BLEU/chrF/WER.

This DOES hit the live engines: it needs a valid key and network, and it
consumes billed minutes. It is a dev/CI tool, never shipped to end users.

Engines: --engine gemini (default) | openai | qwen — built through the same
engines.make_translator factory the app uses, so the bench measures the real
production stack per engine. Input is fed at each engine's ingest rate
(OpenAI 24 kHz, Gemini/Qwen 16 kHz) in realtime.

Key resolution order (per engine):
  gemini: --key > $VOXIS_BENCH_KEY       > BYOK store "developer" slot
  openai: --key > $VOXIS_BENCH_OPENAI_KEY > BYOK store "openai" slot
  qwen:   --key > $VOXIS_BENCH_QWEN_KEY  > config.json "qwen_key"

Fixtures manifest (JSONL), one clip per line:
  {"id":"c1","audio":"fixtures/clip1.wav","target_lang":"en",
   "reference":"<ground-truth translation>","source_ref":"<ground-truth source text>"}

Usage:
  python scripts/bench/run_session.py fixtures/manifest.jsonl -o results.jsonl
  python scripts/bench/run_session.py fixtures/manifest.jsonl --engine openai -o results_oai.jsonl
  python scripts/bench/score.py results.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

# Make the repo importable when run as a script.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

FRAME_MS = 20
SR = 16000
FRAME = SR * FRAME_MS // 1000  # 320 samples
# Matches pipeline._tts_sink's audible gate: an initial near-silent padding
# chunk (OpenAI pads its stream) must not count as "first audio" or the
# latency numbers flatter the padded engine.
AUDIBLE_PEAK = 512
OUT_RATE = 24000  # all three engines emit 24 kHz PCM16


def _resolve_key(cli_key: str | None, engine: str) -> str:
    if cli_key:
        return cli_key
    env_names = {"gemini": "VOXIS_BENCH_KEY", "openai": "VOXIS_BENCH_OPENAI_KEY",
                 "qwen": "VOXIS_BENCH_QWEN_KEY"}
    env = os.environ.get(env_names[engine])
    if env:
        return env
    try:
        if engine == "qwen":
            from app.config import load_config
            k = (load_config() or {}).get("qwen_key")
        else:
            from app import byok_store
            rec = byok_store.load_byok("developer")
            k = rec.get(engine) if isinstance(rec, dict) else rec
        if k:
            return k
    except Exception:
        pass
    raise SystemExit(f"No {engine} key. Pass --key, set ${env_names[engine]}, "
                     "or store one (BYOK store / config.json).")


def _resolve_prod_key(engine: str = "gemini",
                      target: str | None = None) -> tuple[str, str, str | None]:
    """Fetch a PRODUCTION server-issued key (SaaS path) to A/B its tier vs the
    local BYOK key. Needs the env override + the owner's credentials, all
    supplied by the caller's own `!` shell so no secret is relayed:
        VOXIS_OFFICIAL_RELEASE=1 VOXIS_EMAIL=... VOXIS_PW=... ... --prod
    Never prints the key.

    Routing-aware: a bare call is the server's backward-compat path, which
    ALWAYS answers Gemini — so benching any other engine has to ask for routing
    by target and take whatever the server actually picks. The returned engine
    is checked against the requested one rather than assumed, since silently
    benching Gemini while labelling the run 'qwen' is the exact mistake this
    harness exists to avoid. Returns (key, workspace, model); workspace is ''
    off Qwen.

    The MODEL must travel with the key. The server issues a DATED snapshot
    (…-2026-05-19) while resolve_model() falls back to the undated client
    alias, and on DashScope those do not share a quota — so a run that keeps
    the server's key but drops its model benches an id production never uses,
    and can die on an exhausted quota that production is nowhere near.
    """
    if os.environ.get("VOXIS_OFFICIAL_RELEASE") not in ("1", "true", "yes", "on"):
        raise SystemExit("--prod needs VOXIS_OFFICIAL_RELEASE=1 (source override) so login/session-key are enabled.")
    email, pw = os.environ.get("VOXIS_EMAIL"), os.environ.get("VOXIS_PW")
    if not (email and pw):
        raise SystemExit("--prod needs VOXIS_EMAIL and VOXIS_PW env vars.")
    from app import voxis_client
    _, err = voxis_client.pb_login(email, pw)
    if err:
        raise SystemExit(f"login failed: {err}")
    if engine == "gemini" and not target:
        key, *_mid, err = voxis_client.get_session_key()
        got, workspace, model = "gemini", "", None
    else:
        key, got, model, _q, _quota, workspace, _kt, _fallback, err = voxis_client.get_session_key(
            target=target, caps="engine-routing")
    if err or not key:
        raise SystemExit(f"session-key failed: {err}")
    if got and got != engine:
        raise SystemExit(
            f"server routed target={target!r} to engine {got!r}, not {engine!r}. "
            f"Re-run with --engine {got}, or pick a target the server routes to {engine}.")
    print(f"Production session key acquired (not printed): engine={got}"
          + (f", model={model}" if model else "")
          + (f", workspace={workspace}" if workspace else ""))
    return key, (workspace or ""), model


def _load_pcm16(path: str, rate: int) -> bytes:
    """Read any wav/flac, downmix to mono, resample to `rate`, return PCM16 bytes."""
    import soundfile as sf

    from app.audio_io import _make_resampler

    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)  # mono
    if sr != rate:
        x = _make_resampler(sr, rate)(np.ascontiguousarray(x))
    x = np.clip(x, -1.0, 1.0)
    return (x * 32767.0).astype(np.int16).tobytes()


def _bench_cfg(engine: str, clone: str = "off", workspace: str = "") -> dict:
    """Minimal config for engines.make_translator — DEFAULTS so the bench runs
    exactly the app's production translator settings per engine."""
    from app.config import DEFAULTS
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy, no shared mutables
    if engine == "qwen":
        # Defaults are the spike-validated ones (auto source, 500 ms). clone is
        # the one knob the bench varies: it costs first-audio latency and output
        # length, so an A/B needs it addressable rather than pinned off.
        cfg["beta"] = {"enabled": True, "source_lang": "auto", "clone": clone,
                       "hotwords": "", "vad_ms": 500}
        # DashScope keys are workspace-scoped; a key from another Model Studio
        # account needs its own ws-… id (else the built-in default is used).
        # A server-issued key carries its own workspace and must win: pairing it
        # with a stale env/default id 401s the handshake.
        ws = workspace.strip() or os.environ.get("VOXIS_BENCH_QWEN_WS", "").strip()
        if ws:
            cfg["qwen_workspace"] = ws
    return cfg


def run_clip(clip: dict, api_key: str, *, engine: str = "gemini",
             voice: str = "Aoede", clone: str = "off", workspace: str = "",
             model: str | None = None, drain_s: float = 8.0) -> dict:
    from app.engines import make_translator

    heard: list[str] = []   # on_text("in", ...)  -> source transcription
    trans: list[str] = []   # on_text("out", ...) -> translation
    first_audio: dict[str, float | None] = {"t": None}
    started: dict[str, float | None] = {"t": None}
    audio_bytes = {"n": 0, "total": 0}   # audible / all translated audio received
    statuses: list[str] = []
    lock = threading.Lock()

    def on_text(direction: str, text: str):
        with lock:
            (heard if direction == "in" else trans).append(text)

    def on_audio(data: bytes):
        a = np.frombuffer(data, dtype=np.int16)
        audible = a.size > 0 and int(np.abs(a).max()) > AUDIBLE_PEAK
        with lock:
            # Total is every byte the engine emitted; audible drops the silent
            # frames. The overrun ratio that drives playback backlog is a
            # property of the WHOLE stream, so it needs the untrimmed total.
            audio_bytes["total"] += len(data)
            if audible:
                audio_bytes["n"] += len(data)
                if first_audio["t"] is None:
                    first_audio["t"] = time.monotonic()

    def on_status(msg: str):
        statuses.append(str(msg))

    cfg = _bench_cfg(engine, clone=clone, workspace=workspace)
    cfg["gemini_voice"] = voice
    # beta_active is what actually gates cloning (engines.make_translator);
    # without it cfg["beta"]["clone"] is read as "off" and an A/B would silently
    # compare two identical clone-off arms.
    tr = make_translator(cfg, clip["target_lang"], engine=engine, key=api_key,
                         model=model,
                         on_audio=on_audio, on_text=on_text, on_status=on_status,
                         name="bench", beta_active=(clone != "off"))
    tr.start()
    tr.wait_ready(timeout=15)

    in_rate = 24000 if engine == "openai" else SR
    frame = in_rate * FRAME_MS // 1000
    pcm = _load_pcm16(str(ROOT / clip["audio"]) if not os.path.isabs(clip["audio"]) else clip["audio"],
                      in_rate)
    source_s = len(pcm) / (in_rate * 2)
    started["t"] = time.monotonic()
    # Feed at realtime so the measured first-audio latency is realistic.
    step = frame * 2  # bytes per frame (int16)
    for off in range(0, len(pcm), step):
        tr.send_pcm16(pcm[off:off + step])
        time.sleep(FRAME_MS / 1000.0)
    # Let the simultaneous tail finish translating after the audio ends.
    time.sleep(drain_s)
    try:
        tr.stop()
    except Exception:
        pass

    lat = None
    if first_audio["t"] is not None and started["t"] is not None:
        lat = round(first_audio["t"] - started["t"], 3)
    return {
        "id": clip.get("id"),
        "engine": engine,
        "clone": clone,
        "target_lang": clip["target_lang"],
        "reference": clip.get("reference", ""),
        "hypothesis": " ".join(trans).strip(),
        "source_ref": clip.get("source_ref", ""),
        "source_heard": " ".join(heard).strip(),
        "latency_s": lat,
        # Voiced coverage: seconds of AUDIBLE translated speech received vs the
        # source clip's length — the dead-air detector (an engine can emit fine
        # text but little/no voiced audio, which is what the user hears).
        "audio_s": round(audio_bytes["n"] / (OUT_RATE * 2), 2),
        "audio_total_s": round(audio_bytes["total"] / (OUT_RATE * 2), 2),
        "source_s": round(source_s, 2),
        "status_tail": statuses[-3:],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Voxis over a fixtures manifest and capture results.")
    ap.add_argument("manifest", help="JSONL of clips (id, audio, target_lang, reference, source_ref)")
    ap.add_argument("-o", "--out", default="results.jsonl", help="output results JSONL")
    ap.add_argument("--engine", default="gemini", choices=["gemini", "openai", "qwen"],
                    help="translation engine to benchmark (default gemini)")
    ap.add_argument("--key", help="API key for the chosen engine (else env / stored key)")
    ap.add_argument("--prod", action="store_true",
                    help="use the production server-issued key (needs VOXIS_OFFICIAL_RELEASE=1 + VOXIS_EMAIL/VOXIS_PW)")
    ap.add_argument("--voice", default="Aoede")
    ap.add_argument("--clone", default="off", choices=["off", "once", "always"],
                    help="Qwen source-voice cloning (qwen only; costs latency + output length)")
    args = ap.parse_args()

    clips = [json.loads(line) for line in open(args.manifest, encoding="utf-8")
             if line.strip()]
    if not clips:
        raise SystemExit(f"no clips in {args.manifest}")
    if args.prod:
        # Routing is per TARGET language, so the key must be requested for the
        # language actually being benched — the manifest's own target.
        key, workspace, model = _resolve_prod_key(args.engine, clips[0]["target_lang"])
    else:
        key, workspace, model = _resolve_key(args.key, args.engine), "", None
    print(f"Running {len(clips)} clip(s) through engine={args.engine}...")
    with open(args.out, "w", encoding="utf-8") as out:
        for i, clip in enumerate(clips, 1):
            print(f"  [{i}/{len(clips)}] {clip.get('id')} -> {clip['target_lang']}")
            try:
                rec = run_clip(clip, key, engine=args.engine, voice=args.voice,
                               clone=args.clone, workspace=workspace, model=model)
            except Exception as e:
                print(f"    FAILED: {e}")
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
    print(f"Wrote {args.out}. Score it:  python scripts/bench/score.py {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
