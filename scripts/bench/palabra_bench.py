"""Benchmark Palabra.ai's speech-to-speech API on the same fixtures as the
shipped engines, emitting the schema score.py already reads.

Deliberately standalone rather than an engines.make_translator subclass: Palabra
is a vendor under evaluation, not a routing option, so nothing in app/ learns
about it until a number justifies that.

Protocol (docs.palabra.ai): create a session over REST, then stream over a
WebSocket. Audio is base64 PCM s16le 24 kHz mono in ~320 ms chunks, fed at
realtime so first-audio latency is comparable to run_session.py's.

  PALABRA_API_KEY=...  python scripts/bench/palabra_bench.py \
      scripts/bench/fixtures/fleurs/manifest.jsonl --source tr -o results_palabra_tr2en.jsonl
  python scripts/bench/score.py results_palabra_tr2en.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

RATE = 24000           # Palabra's documented default for both directions
CHUNK_MS = 320         # their recommended chunk; smaller ones are rate-limited
OUT_RATE = 24000
# Same audible gate as run_session.py: a leading near-silent chunk must not
# count as first audio, or a padded engine wins the latency column for free.
AUDIBLE_PEAK = 512

SESSION_URL = "https://api.palabra.ai/session-storage/session"
STREAM_HOST = "wss://streaming.palabra.ai/streaming-api"


def _load_pcm16(path: str, rate: int) -> bytes:
    import soundfile as sf
    from app.audio_io import _make_resampler

    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != rate:
        x = _make_resampler(sr, rate)(np.ascontiguousarray(x))
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


def create_session(api_key: str, debug: bool = False) -> tuple[str, str]:
    """Exchange the API key for a streaming endpoint + publisher token.

    Their docs show two shapes (a session-storage POST, and a raw ?token=<key>
    URL). Try the documented POST and fall back to the key itself, so a bench
    run is not blocked by which one this account is provisioned for.
    """
    import requests

    try:
        r = requests.post(SESSION_URL, json={"data": {"subscriber_count": 0}},
                          headers={"ClientId": api_key, "ClientSecret": api_key,
                                   "Content-Type": "application/json"}, timeout=20)
        if debug:
            print(f"  [session] HTTP {r.status_code} {r.text[:400]}")
        if r.ok:
            d = r.json().get("data", r.json())
            d = d.get("data", d)
            tok = d.get("publisher") or d.get("publisher_token") or d.get("token")
            url = d.get("ws_url") or d.get("webrtc_url")
            if tok:
                return (url or STREAM_HOST), tok
    except Exception as e:
        if debug:
            print(f"  [session] POST failed: {e!r}")
    return STREAM_HOST, api_key


def _set_task(source: str, target: str) -> dict:
    return {
        "message_type": "set_task",
        "data": {
            "input_stream": {
                "content_type": "audio",
                "source": {"type": "ws", "format": "pcm_s16le",
                           "sample_rate": RATE, "channels": 1},
            },
            "output_stream": {
                "content_type": "audio",
                "target": {"type": "ws", "format": "pcm_s16le",
                           "sample_rate": RATE, "channels": 1},
            },
            "pipeline": {
                "preprocessing": {},
                "transcription": {"source_language": source},
                "translations": [{"target_language": target,
                                  "speech_generation": {}}],
            },
        },
    }


async def _run_clip(clip: dict, base_url: str, token: str, source: str,
                    drain_s: float, debug: bool) -> dict:
    import websockets

    target = clip["target_lang"]
    heard: list[str] = []
    trans: list[str] = []
    first_audio = {"t": None, "any": None}
    first_text = {"t": None}
    audio = {"audible": 0, "total": 0}
    seen_types: dict[str, int] = {}
    started = {"t": None}

    url = f"{base_url.rstrip('/')}/{uuid.uuid4().hex}/v1/speech-to-speech/stream?token={token}"

    def note_text(msg_type: str, data: dict) -> None:
        """Keep only SETTLED transcriptions.

        `partial_transcription` streams growing prefixes of the same utterance
        ("A", "Aynı", "Aynı ay,"...). Concatenating those inflates the source
        text ~10x and would report a WER of several hundred percent against a
        model that in fact heard the clip correctly. Only `validated_` (source)
        and `translated_` (target) are final.
        """
        tr = data.get("transcription") or data
        text = (tr.get("text") or "").strip()
        if not text:
            return
        if msg_type.startswith("translated_"):
            trans.append(text)
            if first_text["t"] is None:
                first_text["t"] = time.monotonic()
        elif msg_type.startswith("validated_"):
            heard.append(text)

    async with websockets.connect(url, ping_interval=10, ping_timeout=30,
                                  max_size=None) as ws:
        await ws.send(json.dumps(_set_task(source, target)))

        stop = asyncio.Event()
        ready = asyncio.Event()

        async def receiver():
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    return
                if isinstance(raw, bytes):
                    # Some deployments push raw PCM instead of base64 JSON.
                    _take_audio(raw)
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mt = str(msg.get("message_type", "?"))
                seen_types[mt] = seen_types.get(mt, 0) + 1
                data = msg.get("data") or {}
                if mt == "current_task":
                    ready.set()
                if mt == "output_audio_data":
                    b = data.get("data") or ""
                    if b:
                        _take_audio(base64.b64decode(b))
                elif "transcription" in mt:
                    note_text(mt, data)
                elif debug and mt not in ("current_task", "pong"):
                    print(f"    [msg] {mt}: {json.dumps(msg)[:300]}")

        def _take_audio(pcm: bytes) -> None:
            a = np.frombuffer(pcm, dtype=np.int16)
            audio["total"] += len(pcm)
            if first_audio["any"] is None:
                first_audio["any"] = time.monotonic()
            if a.size and int(np.abs(a).max()) > AUDIBLE_PEAK:
                audio["audible"] += len(pcm)
                if first_audio["t"] is None:
                    first_audio["t"] = time.monotonic()

        rx = asyncio.create_task(receiver())
        # Wait for the server to confirm the pipeline is live. A blind sleep here
        # races set_task: audio sent before the task exists is discarded, which
        # looks exactly like a vendor that silently produced nothing.
        try:
            await asyncio.wait_for(ready.wait(), timeout=15)
        except asyncio.TimeoutError:
            print("    WARN: no current_task confirmation; feeding anyway")
        await asyncio.sleep(0.2)

        path = clip["audio"]
        pcm = _load_pcm16(str(ROOT / path) if not os.path.isabs(path) else path, RATE)
        step = RATE * CHUNK_MS // 1000 * 2
        started["t"] = time.monotonic()
        # Schedule against the clip's own clock, not a fixed sleep: send cost
        # accumulates over 45 chunks and would feed slower than realtime, which
        # inflates every latency number by the drift.
        for i, off in enumerate(range(0, len(pcm), step)):
            await ws.send(json.dumps({
                "message_type": "input_audio_data",
                "data": {"data": base64.b64encode(pcm[off:off + step]).decode()},
            }))
            due = started["t"] + (i + 1) * CHUNK_MS / 1000.0
            await asyncio.sleep(max(0.0, due - time.monotonic()))
        await asyncio.sleep(drain_s)
        stop.set()
        await asyncio.wait_for(rx, timeout=5)

    def _since(t):
        return round(t - started["t"], 3) if (t and started["t"]) else None

    return {
        "id": clip.get("id"),
        "engine": "palabra",
        "target_lang": target,
        "reference": clip.get("reference", ""),
        "hypothesis": " ".join(trans).strip(),
        "source_ref": clip.get("source_ref", ""),
        "source_heard": " ".join(heard).strip(),
        "latency_s": _since(first_audio["t"]),
        # Splits the wait into its two halves: how long until the translation
        # EXISTS as text, vs the extra cost of speaking it. A vendor claiming
        # sub-second latency may be quoting one of these, not the sum.
        "text_latency_s": _since(first_text["t"]),
        "any_audio_s": _since(first_audio["any"]),
        "audio_s": round(audio["audible"] / (OUT_RATE * 2), 2),
        "audio_total_s": round(audio["total"] / (OUT_RATE * 2), 2),
        "source_s": round(len(pcm) / (RATE * 2), 2),
        "msg_types": seen_types,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Bench Palabra.ai S2S on Voxis fixtures.")
    ap.add_argument("manifest")
    ap.add_argument("-o", "--out", default="results_palabra.jsonl")
    ap.add_argument("--source", required=True, help="source language code (e.g. tr, en)")
    ap.add_argument("--key", help="API key (else $PALABRA_API_KEY)")
    ap.add_argument("--limit", type=int, help="only run the first N clips")
    ap.add_argument("--drain", type=float, default=8.0)
    ap.add_argument("--debug", action="store_true", help="dump unrecognised messages")
    args = ap.parse_args()

    key = args.key or os.environ.get("PALABRA_API_KEY")
    if not key:
        raise SystemExit("No key: pass --key or set $PALABRA_API_KEY.")

    clips = [json.loads(line) for line in open(args.manifest, encoding="utf-8") if line.strip()]
    if args.limit:
        clips = clips[:args.limit]
    if not clips:
        raise SystemExit(f"no clips in {args.manifest}")

    base_url, token = create_session(key, args.debug)
    print(f"Running {len(clips)} clip(s) through Palabra ({args.source} -> "
          f"{clips[0]['target_lang']})...")
    with open(args.out, "w", encoding="utf-8") as out:
        for i, clip in enumerate(clips, 1):
            print(f"  [{i}/{len(clips)}] {clip.get('id')}")
            try:
                rec = asyncio.run(_run_clip(clip, base_url, token, args.source,
                                            args.drain, args.debug))
            except Exception as e:
                print(f"    FAILED: {e!r}")
                continue
            print(f"    audio_lat={rec['latency_s']}s text_lat={rec['text_latency_s']}s "
                  f"voiced={rec['audio_s']}s/{rec['source_s']}s")
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
    print(f"Wrote {args.out}. Score it:  python scripts/bench/score.py {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
