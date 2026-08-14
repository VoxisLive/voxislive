"""Mode pipelines: capture → VAD gate → Gemini Live → playback.

IncomingPipeline routes system audio (or the meeting partner's voice) to the
translator and sends the synthesized translation to the user's headphones.
OutgoingPipeline routes the user's microphone to the translator and pipes the
translation into the virtual microphone consumed by Teams/Zoom/etc.
"""
import collections
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable

import numpy as np

from . import audio_io, sysaudio, voxis_client
from .audio_io import Capture, Player, _make_resampler, find_device, resolve_name
from .base_translator import BaseTranslator, _WatchdogExhausted
from .cascade_translator import CascadeTranslator
from .config import (
    ENGINE_CASCADE,
    ENGINE_GEMINI,
    ENGINE_QWEN,
    gate_params,
    resolve_voice,
    stream_gated,
)
from .engines import make_translator
from .i18n import t
from .playback_sync import AdaptivePlaybackStager

_log = logging.getLogger("voxis")

# Open-Core hook: optional premium package resolved once at import time.
# Absence is the normal OSS path.
try:
    import premium as _premium  # type: ignore[import-not-found]
except ImportError:
    _premium = None
# LiveTranslator (google.genai) and SpeechGate (onnxruntime) are imported lazily
# inside the pipeline constructors so the heavy runtimes don't load until a
# session actually starts — shaving ~1-2 s off cold app startup.
_FRAME = 512  # 32 ms @ 16 kHz — Silero VAD v5 frame size
# Translated-speech sample rate every engine emits (PCM16 mono). Only used to
# convert produced BYTES into seconds for the audio track; the playback path
# still passes 24000 explicitly where it configures devices.
TTS_RATE = 24000


def _f32_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def _rms_level(prev: float, mono: np.ndarray, gain: float = 6.0) -> float:
    """Asymmetric-smoothed input level (0..1) for the UI meter: fast attack, slow
    release. Drives only telemetry — never the audio path."""
    if mono.size == 0:
        target = 0.0
    else:
        rms = float(np.sqrt(np.mean(mono.astype(np.float32) ** 2)))
        target = min(1.0, rms * gain)
    a = 0.5 if target > prev else 0.12
    return prev + (target - prev) * a


class RTTEstimator:
    """Estimates cloud round-trip time (speech onset → first TTS chunk) with EMA
    smoothing. The estimate drives the ambient delay line so the original audio
    stays aligned with the translation when the spatial path is engaged.

    The alignment is utterance-level, not sample-accurate — translation reorders
    and re-times words, so this only locks onsets. Onsets that fire while TTS is
    already playing are skipped to avoid contaminated samples.
    """

    def __init__(self, fs: float, ema_alpha: float = 0.1,
                 min_seconds: float = 0.2, max_seconds: float = 3.0):
        self.fs = float(fs)
        self.alpha = float(ema_alpha)
        self.min_s = float(min_seconds)
        self.max_s = float(max_seconds)
        self._ema = None            # guarded EMA for the ambient delay line
        self._t_onset = None
        self._t_first_onset = None  # first speech onset of the session
        self._first_audio_s = None  # session first-audio latency (display/analysis)
        self._lock = threading.Lock()

    def mark_onset(self) -> None:
        """Guarded onset (delay-line): the caller skips it while TTS is playing."""
        with self._lock:
            if self._t_onset is None:
                self._t_onset = time.monotonic()

    def mark_first_onset(self) -> None:
        """Records the session's FIRST speech time (no guards), for the honest
        first-audio readout — captured even if TTS is already playing."""
        with self._lock:
            if self._t_first_onset is None:
                self._t_first_onset = time.monotonic()

    def mark_tts(self, audible: bool = True) -> None:
        with self._lock:
            now = time.monotonic()
            # Honest, backlog-proof readout: span from the session's FIRST speech
            # to the FIRST AUDIBLE translated audio. Measured ONCE, before any
            # backlog exists, so it's comparable across engines — unlike a
            # per-utterance onset→next-chunk reading, which a continuously-playing
            # engine (still playing a previous translation when the next utterance
            # starts) drives to a meaningless ~0.0-0.2 s. Gating on audible output
            # ignores an initial near-silent/padding chunk that would understate it.
            if audible and self._first_audio_s is None and self._t_first_onset is not None:
                fa = now - self._t_first_onset
                if 0.1 <= fa <= 30.0:
                    self._first_audio_s = round(fa, 2)
            # Delay-line EMA from the GUARDED onset only (uncontaminated), capped.
            if self._t_onset is not None:
                dt = now - self._t_onset
                self._t_onset = None
                if self.min_s <= dt <= self.max_s:
                    self._ema = dt if self._ema is None else self.alpha * dt + (1 - self.alpha) * self._ema

    def target_samples(self) -> float:
        with self._lock:
            return 0.0 if self._ema is None else self._ema * self.fs

    @property
    def rtt_seconds(self) -> float | None:
        return self._ema

    @property
    def first_audio_seconds(self) -> float | None:
        """Session first-audio latency (first speech → first translated audio) for
        the UI/analysis readout — backlog-proof and comparable across engines."""
        return self._first_audio_s

    @property
    def speech_seen(self) -> bool:
        """Whether the VAD ever reported a speech onset this session. Reads the
        marker the first-audio readout already sets, so it costs nothing extra:
        it is the only signal that separates "we never heard anything to
        translate" from "audio flowed but no translation came back"."""
        return self._t_first_onset is not None


# Smart-stream silence ceiling: after this many consecutive non-speech frames
# stop padding with silence. ~512/16000 s per frame, so 48 frames ≈ 1.5 s of
# trailing pad before we let a genuine gap form. The gap lets the translator's
# bounded input queue drain to empty, which is what allows the _sender's 0.5 s
# read timeout to surface and the 13-min rotation to fire on a quiet window.
# Billing tradeoff: Smooth (smart=True) streams continuous audio, so this pad
# is the only thing that bounds billed silence; Saver (gated) never pads, so it
# bills fewer minutes at the cost of clipped lead-ins on the next utterance.
_SMART_SILENCE_MAX_FRAMES = 48


class _Accum:
    """Preallocated float32 frame accumulator: append chunks, pop fixed-size
    frames. Replaces the per-chunk np.concatenate churn (the same realloc
    pattern the playback ring was rewritten to eliminate) with two slice copies
    per cycle and zero steady-state allocation beyond the popped frame."""

    __slots__ = ("_buf", "n")

    def __init__(self, cap: int):
        self._buf = np.empty(cap, dtype=np.float32)
        self.n = 0

    def push(self, x: np.ndarray) -> None:
        m = len(x)
        if m == 0:
            return
        need = self.n + m
        if need > len(self._buf):  # rare: grow geometrically, then stabilize
            nb = np.empty(max(need, 2 * len(self._buf)), dtype=np.float32)
            nb[:self.n] = self._buf[:self.n]
            self._buf = nb
        self._buf[self.n:need] = x
        self.n = need

    def pop(self, k: int) -> np.ndarray:
        """Remove and return the first k samples as an independent copy (the
        gate stores frames across calls, so views into _buf are not safe)."""
        out = self._buf[:k].copy()
        rem = self.n - k
        if rem:
            self._buf[:rem] = self._buf[k:self.n]
        self.n = rem
        return out


class _GatedSource:
    """Resamples captured audio to 16 kHz, splits into 512-sample frames and runs
    each frame through the VAD gate.

    Modes:
      * default: gated — only speech frames are forwarded to the translator.
      * smart:   continuous stream; speech frames are real audio, non-speech
                 frames become silence. Keeps latency low while music/noise is
                 filtered out before reaching the cloud. After a sustained gap
                 silence padding stops so the queue can drain and rotation fire.
      * always_send: raw continuous stream, including silence (legacy agent path).
    """

    def __init__(self, in_rate: int, gate, send_fn, suppress_when=None,
                 always_send=False, smart=False, speech_tap=None):
        self._in_rate = int(in_rate)
        self._resample = _make_resampler(in_rate, 16000)
        self._gate = gate
        self._send = send_fn
        self._suppress_when = suppress_when
        # Optional observer of the gate's speech decisions (16 kHz frames incl.
        # preroll) — feeds the speaker-change tracker. Must be O(1)/non-raising:
        # it runs on the capture thread under this object's lock.
        self._speech_tap = speech_tap
        self._always_send = always_send
        self._smart = smart
        self._silence = _f32_to_pcm16(np.zeros(_FRAME, dtype=np.float32))
        self._acc = _Accum(8 * _FRAME)
        self._lock = threading.Lock()
        self._silent_run = 0
        self.speech_active = False
        self.closed = False

    def feed(self, chunk: np.ndarray):
        if self.closed:
            return
        # Classic loopback path zeros the input while TTS is playing so the
        # translator never re-translates its own output. Sending silence (not
        # nothing) preserves stream continuity.
        if self._suppress_when is not None and self._suppress_when():
            chunk = np.zeros_like(chunk)
        with self._lock:
            self._acc.push(self._resample(chunk))
            while self._acc.n >= _FRAME:
                frame = self._acc.pop(_FRAME)
                active, to_send = self._gate.process(frame)
                self.speech_active = active
                if self._speech_tap is not None and to_send:
                    try:
                        self._speech_tap(to_send)
                    except Exception:
                        pass  # labeling is best-effort; never break capture
                if self._smart:
                    if to_send:
                        self._silent_run = 0
                        self._emit(to_send)
                    elif self._silent_run < _SMART_SILENCE_MAX_FRAMES:
                        # Pad short gaps to keep the model's stream continuous,
                        # but stop once the gap is genuine so the queue drains
                        # and rotation can fire on the quiet window.
                        self._silent_run += 1
                        self._emit_silence()
                elif self._always_send:
                    self._emit([frame])
                else:
                    self._emit(to_send)

    def _emit(self, frames16):
        """Forward the gate's decided frames to the engine.

        Every engine ingests 16 kHz (Gemini, Qwen, cascade), so the gate's own
        frames ARE the wire frames. A parallel full-band path existed here for a
        24 kHz engine (OpenAI, retired 2026-07-23); with send_rate pinned to
        16000 at both call sites it was unreachable, so it was removed along with
        the per-chunk / per-frame branches it cost this hot path. Recovering it
        means pulling it back from git history, not flipping a flag."""
        if not frames16:
            return
        for f in frames16:
            self._send(_f32_to_pcm16(f))

    def _emit_silence(self):
        self._send(self._silence)


class IncomingPipeline:
    # Class-level default so the metering path never depends on how far __init__
    # got: _ingest_input runs on the capture thread and must not raise on an
    # attribute lookup (a fault there would make a healthy signal look like
    # silence, which is the opposite of what this telemetry is for).
    peak_input_level: float = 0.0

    def __init__(self, cfg: dict, resolve, mode: str, on_text, on_status,
                 session_dir: str | None = None, on_speaker=None):
        # Default the premium flag before either capture branch so callers and
        # teardown can always read it, even on the driverless path that never
        # probes premium hardware.
        self._use_premium = False
        self._sducker = None
        self._routing_handle = None
        self.capture = None
        # These three are unset only for the brief window between construction
        # and start() (which always sets them before returning); every reader
        # below (including nested capture-thread callbacks defined inside
        # start()) only runs once the pipeline is live. Declared non-Optional
        # so those call sites don't all need their own None-guard; the actual
        # deferred-init gap is acknowledged once, right here.
        self._source: _GatedSource = None  # pyright: ignore[reportAttributeAccessIssue]
        self._recorder = None
        self.player: Player = None  # pyright: ignore[reportAttributeAccessIssue]
        self.translator: BaseTranslator | CascadeTranslator = None  # pyright: ignore[reportAttributeAccessIssue]
        self._stager = None
        self._mode = mode
        self._spk_tracker = None
        # Per-session output folder (transcript + WAVs share it); None → the
        # recorder falls back to the flat transcripts root.
        self._session_dir = session_dir
        vad_cfg = gate_params(cfg)
        # Playback target: fall back to the system default (with a warning) when
        # the configured device is absent — a config carried over from another
        # machine, or a renamed/unplugged endpoint, must not hard-fail the whole
        # session. The CABLE feedback guard below still rejects a bad default.
        out_dev = find_device(cfg["devices"]["headphones_output"], "output",
                              on_status=on_status, fallback_default=True)
        out_name = resolve_name(out_dev, "output")
        if "CABLE" in out_name or "VB-Audio" in out_name:
            raise ValueError(
                f"Translation output is routed to a virtual cable ({out_name}). "
                "This creates a feedback loop. Set devices.headphones_output in "
                "config.json to the real headphone device (list devices with: "
                "python -m app.audio_io)."
            )
        # Read by ModeController._start_volume_mirror to neutralize this exact
        # device's own endpoint level in vbcable mode (see endpoint_volume.py).
        self._out_device_name = out_name

        self.player = Player(
            out_dev, tts_in_rate=24000,
            max_ambient_delay_ms=float(cfg.get("max_ambient_delay_ms", 400)),
            # Premium voice-enhancement runs on every official path (incl.
            # driverless, where the spatial split never fires). Absent on the OSS
            # build (_premium is None), so the TTS stream is untouched there.
            tts_enhance=(_premium.enhance_tts if _premium is not None else None),
        )
        self.player.tts_gain = float(cfg.get("tts_volume", 1.0))
        self._rtt = RTTEstimator(self.player.rate)
        # UI telemetry: smoothed input level (0..1) and speech-onset edge tracking.
        self.input_level = 0.0
        # Loudest level seen this session. The instantaneous meter is smoothed with
        # a slow release, so it can read ~0 during an ordinary pause; the running
        # peak is what answers "did ANY audio ever reach us", which is the question
        # the no-input notice asks.
        self.peak_input_level = 0.0
        self._prev_active = False

        # Optional speaker-change tracker (incoming direction only). Construct it
        # after Player succeeds so an earlier device-resolution failure cannot
        # orphan the tracker's worker thread.
        if on_speaker is not None and cfg.get("speaker_labels", True):
            try:
                from .speaker_id import SpeakerTracker
                self._spk_tracker = SpeakerTracker(on_change=on_speaker)
            except Exception:
                _log.exception("speaker tracker init failed — labels disabled")

        # Resolve engine + key + model for this target ONCE (locally for BYOK,
        # server-side for SaaS) so the capture send-rate matches the engine.
        try:
            self._engine, _key, _model, _fallback = resolve(cfg["target_language_incoming"])
        except Exception:
            self._teardown_resources()
            raise
        # Kept for the mid-session engine substitution below.
        self.cfg = cfg
        self._resolve = resolve
        self._on_status = on_status
        self._on_text = on_text
        self._failover_done = False

        # Gemini and Qwen can deliver a long translated turn faster than
        # realtime. Pace their already-generated audio through a client-side
        # WSOLA stager so an accumulating playback tail catches up to the live
        # captions without raising the voice's pitch. Cascade controls speed
        # while synthesizing locally, so it needs no stager.
        if self._engine in (ENGINE_GEMINI, ENGINE_QWEN):
            try:
                self._stager = AdaptivePlaybackStager(
                    self.player, on_status=on_status, input_rate=24000)
            except Exception:
                self._teardown_resources()
                raise

        # While the free-voice preview speaks, the paid voice stands down: two
        # voices over one another would demo nothing. Captions keep flowing and
        # the recorder keeps its faithful copy of what the engine produced —
        # only playback is withheld, and only for the length of the clip.
        self._preview_mute = False
        # A few seconds of the paid voice, kept so it can be replayed back-to-back
        # against the free voice AFTER the session — which is the only moment the
        # user is reliably looking at Voxis rather than at what they came to watch.
        # Bounded and audible-only: silence would replay as a dead button.
        self._pro_ring: collections.deque = collections.deque()
        self._pro_ring_bytes = 0
        # Cumulative seconds of translated speech the engine has produced this
        # session (see _tts_sink). Read by the bridge to record an audio track
        # alongside the caption track, so "this text was never spoken" becomes
        # measurable instead of anecdotal.
        self._tts_seconds = 0.0
        self._tts_rate = TTS_RATE

        def _tts_sink(data: bytes):
            # Counted FIRST, before any branch that can return early (preview
            # mute, cascade): this is "how much translated speech the engine
            # produced", not "how much reached the speakers". A field session
            # spoke only ~90 % of the words its captions showed and there was no
            # way to see where the rest went — the caption stream was recorded,
            # the audio stream was not. Bytes -> seconds at the engine's own
            # output rate; PCM16 mono, hence /2.
            self._tts_seconds += len(data) / (self._tts_rate * 2)
            # Gate the first-audio metric on AUDIBLE output: an initial near-silent
            # / padding chunk would otherwise understate latency.
            a = np.frombuffer(data, dtype=np.int16)
            audible = a.size > 0 and int(np.abs(a).max()) > 512
            self._rtt.mark_tts(audible=audible)
            if self._recorder is not None:
                self._recorder.feed_translated(data)
            if self._preview_mute:
                return          # not heard → not part of "what you just heard"
            if audible and self._engine != ENGINE_CASCADE:
                # The A/B card labels this ring "Pro voice". A cascade session
                # flows through the same sink — record its Piper audio here and
                # the comparison would play the free voice under a Pro label.
                self._keep_pro_audio(data)
            if self._stager is not None:
                self._stager.feed(data)
            else:
                self.player.feed_tts_pcm16(data)
        self._tts_sink = _tts_sink
        try:
            self.translator = make_translator(
                cfg, cfg["target_language_incoming"], engine=self._engine, key=_key,
                model=_model, on_audio=_tts_sink, on_text=on_text,
                on_status=on_status, name=t("name_in"),
                # Gemini failover is a PAID perk (2026-08-12 cost-pressure
                # policy — see .vault/decision-log.md): free/taste sessions
                # never buy a Gemini fallback. A free/taste session still
                # inside its one-time 15-minute Pro taste instead gets a
                # shot at the cascade rescue (_swap_to_cascade) — server-
                # granted only, see that function's docstring. Anyone else
                # (taste already spent, Meeting mode — the incoming leg of a
                # meeting reaches here too, but the server refuses to
                # cascade a meeting regardless of this wiring) falls through
                # to None: BaseTranslator._give_up just surfaces the
                # existing connection-error status.
                on_fatal=(self._failover_to_gemini if cfg.get("_paid_customer")
                         else self._failover_to_cascade
                         if cfg.get("_taste_rescue_eligible") else None),
                # SaaS resolvers hang the Gemini key fountain off the resolve fn so
                # a single-use ephemeral key can be refreshed on every rotation
                # (dev/BYOK resolvers carry none — raw keys need no refetch).
                key_provider=getattr(resolve, "gemini_key_provider", None),
                # Qwen voice-cloning only when this is a real beta session (webui
                # sets it on the beta resolver); off on the standard Qwen route.
                beta_active=getattr(resolve, "beta_active", False),
                # Each leg resolves its OWN voice: a meeting speaks with two
                # genders and both legs share this cfg.
                voice=resolve_voice(self._engine,
                                    cfg.get("voice_gender_incoming", "auto")),
                fallback=_fallback,
            )
        except Exception:
            self._teardown_resources()
            raise
        # Bound through self, not to the translator instance, so a mid-session
        # engine swap redirects the capture without rebuilding the gate/capture.
        def send_fn(pcm: bytes):
            self.translator.send_pcm16(pcm)

        self._original_mode = cfg["original_audio"]
        self._duck_gain = cfg["duck_gain"]
        self.driverless = cfg.get("capture_backend", "driverless") != "vbcable"

        # Acquire OS resources (COM/pycaw ducker, capture, gate) under one guard:
        # a mid-init failure on any line must release the ones already held, or a
        # rejected start() leaks a SessionDucker COM handle or an open WASAPI
        # capture that keeps the device busy on the next retry.
        try:
            self._acquire_capture(cfg, vad_cfg, send_fn, out_name, on_status)
        except Exception:
            self._teardown_resources()
            raise

    def _failover_to_gemini(self, exc) -> bool:
        return _swap_to_gemini(self, "target_language_incoming", t("name_in"), exc)

    def _failover_to_cascade(self, exc) -> bool:
        return _swap_to_cascade(self, "target_language_incoming", t("name_in"), exc)

    def _apply_original_gain(self, speaking: bool) -> float:
        """Compute the "original audio" duck level, on the VB-CABLE path (the
        driverless path steers the session ducker instead, in `on_loop`). `mix`
        leaves the original alone, `mute_during_speech` silences it while anyone
        is talking, and the default ducks it to `duck_gain`.

        Also note this is a DUCK: it only acts while someone is speaking (the
        label says so). With the stream idle the level sits at 1.0 by design.

        WHO CONSUMES THE RETURNED LEVEL DEPENDS ON WHO IS SUPPRESSING THE DIALOGUE:

          * premium (ADRess): the caller feeds this level into
            `execute_vocal_split(..., level=)` as the per-bin centre floor, so
            the slider ducks the SPEAKER directly -- the mixer's `mid_gain` /
            `ambient_gain` stay at 1.0 here, i.e. the sides (music/SFX) are
            NEVER touched by this control. An earlier version routed the level
            to `ambient_gain` (the whole remaining program, sides included) on
            the theory that ADRess's own fixed -18 dB floor already handled the
            speaker -- that inverted the control (it ducked music instead of the
            voice, and defeated the entire point of the music-preserving VB-CABLE
            path) and was reverted the same day it shipped. Field report,
            2026-07-25.
          * OSS / no premium: broadband mid subtraction IS the only dialogue
            suppression available, so the level drives `mid_gain` directly --
            unchanged behaviour, and the music in the sides survives.

        It lives in its own method for two reasons. It USED to sit inside
        `on_chunk`'s non-premium `else`, so on the premium path neither gain was
        ever assigned. And a closure buried in `_acquire_capture`, which opens
        real devices, could not be tested; this can
        (`tests/test_original_audio_control.py`).
        """
        # Smooth ramp (~80 ms) so the gain transition does not click.
        self._speak += ((1.0 if speaking else 0.0) - self._speak) * 0.25
        if self._original_mode == "mix":
            level = 1.0
        elif self._original_mode == "mute_during_speech":
            level = 1.0 - self._speak
        else:
            level = 1.0 - self._speak * (1.0 - self._duck_gain)
        level = float(level)
        if not self._use_premium:
            self.player.mid_gain = level
        return level

    def _stream_is_gated(self, cfg) -> bool:
        """Cascade (free tier) ALWAYS streams gated — cloud input tokens are its
        whole bill, and omitting silence roughly halves them on film content.
        Paid engines keep the preset's choice (Saver gated, the rest smart)."""
        return stream_gated(cfg) or self._engine == ENGINE_CASCADE

    def _ingest_input(self, mono: np.ndarray) -> None:
        """Account for raw captured audio before optional consumers process it.

        The UI meter is capture telemetry, not VAD/translator telemetry. Keep it
        truthful even when recording or speech processing raises; the capture
        worker reports that downstream failure through its liveness channel.
        """
        self.input_level = _rms_level(self.input_level, mono)
        if self.input_level > self.peak_input_level:
            self.peak_input_level = self.input_level
        if self._recorder is not None:
            self._recorder.feed_source(mono)
        self._source.feed(mono)

    def _acquire_capture(self, cfg, vad_cfg, send_fn, out_name, on_status):
        from .vad import SpeechGate
        # Every current engine ingests 16 kHz and the VAD runs at 16 kHz, so the
        # capture, the gate and the wire all share one rate — _GatedSource no
        # longer carries a second, engine-facing rate (see its _emit).
        wire_rate = 16000
        if self.driverless:
            # Driverless mode: system audio loopback; ducking is applied so the
            # user hears a real dubbing effect without any virtual-cable
            # install. Windows: WASAPI loopback + per-app session-volume API.
            # Linux: Option-A routing (VoxisCapture + ducked loopback) --
            # make_capture_routing is a no-op returning None on Windows, so
            # this line changes nothing there.
            self._routing_handle = sysaudio.make_capture_routing()
            self._sducker = sysaudio.make_ducker(routing_handle=self._routing_handle)

            def on_loop(chunk: np.ndarray):
                # Bound once per call: set just above, cleared only on teardown
                # (after the capture that invokes this callback has stopped).
                sducker = self._sducker
                assert sducker is not None
                lvl = sducker.current
                # Windows' ducker attenuates the SAME mix its loopback then
                # captures, so the level must be compensated back up for
                # VAD/Gemini. Linux's capture point sits upstream of the duck
                # (see ducking.LinuxSessionDucker.duck_affects_capture) so it
                # is never tainted in the first place -- compensating it too
                # would wrongly amplify already-full-level audio.
                if getattr(sducker, "duck_affects_capture", True) and lvl < 0.95:
                    chunk = np.clip(chunk / max(lvl, 0.15), -1.0, 1.0)
                # Observe the raw capture before VAD/translator work. A consumer
                # fault must not make a healthy WASAPI signal look like −∞ dB;
                # the capture liveness path reports that downstream fault apart.
                self._ingest_input(chunk)
                # Mark speech onset here too (the spatial path does it in vbcable
                # mode) so the ear-voice latency readout populates in driverless.
                active = self._source.speech_active
                if active and not self._prev_active:
                    self._rtt.mark_first_onset()  # session first-speech (no guard)
                    if not self.player.tts_active:
                        self._rtt.mark_onset()
                self._prev_active = active
                speaking = self._source.speech_active or self.player.tts_active
                if self._original_mode == "mix":
                    sducker.target = 1.0
                elif self._original_mode == "mute_during_speech":
                    sducker.target = 0.0 if speaking else 1.0
                else:
                    sducker.target = self._duck_gain if speaking else 1.0

            suppress: Callable[[], bool] | None = None
            # Preferred path on Win10 2004+: process-exclude loopback. Our own TTS
            # is excluded at the hardware level so the translator keeps receiving
            # input even while playback is active. Activation can fail TRANSIENTLY
            # (COM race / the 5 s activation timeout when the audio service is busy
            # at startup); that failure would drop the session onto the classic
            # loopback path, whose echo-suppress zeroes the input while TTS plays —
            # on continuous speech that silences everything after the first
            # utterance. Retry a few times before accepting the degraded fallback so
            # a transient hiccup doesn't break the whole session. A genuinely
            # unsupported OS fails fast (immediate HRESULT, no 5 s wait), so the
            # retries cost little there.
            self.capture = None
            pe_err = None
            for attempt in range(3):
                try:
                    self.capture = sysaudio.make_process_loopback(
                        on_loop, rate=wire_rate, routing_handle=self._routing_handle)
                    pe_err = None
                    break
                except Exception as e:
                    pe_err = e
                    self.capture = None
                    if attempt < 2:
                        time.sleep(0.6)
            if self.capture is None:
                # Genuinely unavailable after retries — fall back, but surface a
                # clear, actionable warning (impact + remedy) instead of a silent
                # half-working session. The error rides along for field diagnosis.
                on_status(t("st_classic_capture_warning", e=pe_err))
                self.capture = sysaudio.make_loopback_capture(
                    on_loop, prefer_name=out_name, on_status=on_status)
                def _suppress_while_tts_active():
                    return self.player.tts_active
                suppress = _suppress_while_tts_active
            self._source = _GatedSource(
                self.capture.rate, SpeechGate(**vad_cfg), send_fn,
                suppress_when=suppress, smart=not self._stream_is_gated(cfg),
                speech_tap=self._spk_tracker.feed if self._spk_tracker else None,
            )
        else:
            # VB-CABLE: audio is intercepted before reaching the speakers. The
            # capture is stereo and we apply M/S center-suppression so the
            # original dialogue (Mid) is ducked while stereo music/SFX (Side)
            # is preserved. The TTS sits in the phantom center.
            cap_dev = find_device(cfg["devices"]["system_capture"], "input")
            self._use_premium = _premium is not None and _premium.hardware_ok()
            self._speak = 0.0
            self._prev_active = False

            def on_chunk(chunk: np.ndarray):
                mono = chunk.mean(axis=1) if chunk.ndim > 1 else chunk
                self._ingest_input(mono)
                active = self._source.speech_active
                if active and not self._prev_active:
                    self._rtt.mark_first_onset()  # session first-speech (no guard)
                    if not self.player.tts_active:
                        self._rtt.mark_onset()
                self._prev_active = active
                self.player.delay_target_samples = self._rtt.target_samples()
                speaking = self._source.speech_active or self.player.tts_active
                level = self._apply_original_gain(speaking)
                if self._use_premium:
                    assert _premium is not None  # _use_premium is only True when set
                    processed = _premium.execute_vocal_split(chunk, speaking, level)
                    self.player.feed_passthrough(processed)
                else:
                    self.player.feed_passthrough(chunk)

            self.capture = Capture(cap_dev, on_chunk, stereo=True)
            # Match the ambient resampler to the capture device's true rate so the
            # M/S passthrough never clicks on a capture/playback clock mismatch.
            self.player.configure_passthrough(self.capture.rate)
            self._source = _GatedSource(
                self.capture.rate, SpeechGate(**vad_cfg), send_fn,
                smart=not self._stream_is_gated(cfg),
                speech_tap=self._spk_tracker.feed if self._spk_tracker else None,
            )

        # One-shot capture diagnostic (rendered in the transcript, so a field
        # report — "translation stops after the first line" — can be mapped to the
        # path that produced it without a repro). The two paths that can starve the
        # model on continuous speech are the classic-loopback echo-suppress
        # (suppress=True zeroes input while TTS plays) and original=mute_during_speech.
        on_status(
            "capture: backend={} mode={} suppress={} smart={} original={} duck={:.2f} engine={} rate={:d}".format(
                type(self.capture).__name__,
                "vbcable" if not self.driverless else "driverless",
                self._source._suppress_when is not None,
                self._source._smart,
                cfg.get("original_audio"),
                float(cfg.get("duck_gain", 0.0)),
                self._engine,
                wire_rate,
            )
        )

        # Opt-in dual-track recorder (default OFF). Created here so the source WAV
        # rate matches the capture's true rate (self.capture.rate — the rate the
        # source-tap chunks are delivered at, on both the driverless and vbcable
        # paths). Any failure is non-fatal: a broken recorder must never stop a
        # translation session.
        # Recording is a VIDEO/GAME-mode capability only. In meeting mode the
        # source track is another person's live voice, which recording without
        # their consent is legally fraught (all-party-consent jurisdictions), so
        # we never record it — regardless of the opt-in toggle. The toggle's UI
        # hint states this; here we just skip + log so the behavior is traceable.
        if cfg.get("record_audio") and self._mode == "meeting":
            _log.info("audio recording skipped in meeting mode (two-party consent)")
        if cfg.get("record_audio") and self._mode != "meeting":
            try:
                from . import paths
                from .audio_recorder import DualTrackRecorder
                # Write into this session's own folder (so the WAVs sit beside the
                # transcript JSON and share its stamp); fall back to the flat root
                # when no session folder was supplied (non-webui callers).
                out_dir = self._session_dir or paths.transcripts_dir(cfg)
                stamp = None
                if self._session_dir:
                    base = os.path.basename(self._session_dir.rstrip("\\/"))
                    stamp = base[len("voxis_"):] if base.startswith("voxis_") else base
                self._recorder = DualTrackRecorder(
                    out_dir, source_rate=self.capture.rate,
                    tag=self._mode or "video", stamp=stamp, on_status=on_status)
            except Exception:
                self._recorder = None
                _log.exception("audio recorder init failed — continuing without it")

    def _teardown_resources(self):
        """Release whatever resources were acquired. Safe to call with partial
        init: each handle is closed independently and best-effort. Includes the
        Player and translator (both opened before the capture guard) so an open
        OutputStream / Live socket does not leak when init fails mid-way."""
        if self._source is not None:
            self._source.closed = True
        cap = self.capture
        if cap is not None:
            try:
                cap.stop()
            except Exception:
                pass
        duck = self._sducker
        if duck is not None:
            try:
                duck.close()
            except Exception:
                pass
            self._sducker = None
        handle = self._routing_handle
        if handle is not None:
            try:
                sysaudio.teardown_capture_routing(handle)
            except Exception:
                pass
            self._routing_handle = None
        for attr in ("_stager", "player", "translator", "_recorder", "_spk_tracker"):
            comp = getattr(self, attr, None)
            if comp is not None:
                try:
                    comp.stop()
                except Exception:
                    pass

    # ~8 s of paid voice at 24 kHz PCM16 — long enough to recognise a voice,
    # short enough that the ring is never a memory concern.
    PRO_RING_BYTES = 8 * 24000 * 2

    def _keep_pro_audio(self, data: bytes):
        self._pro_ring.append(data)
        self._pro_ring_bytes += len(data)
        while self._pro_ring_bytes > self.PRO_RING_BYTES and len(self._pro_ring) > 1:
            self._pro_ring_bytes -= len(self._pro_ring.popleft())

    def recent_pro_pcm(self) -> bytes:
        """The last few seconds the paid voice actually SPOKE. Survives stop() on
        purpose: the A/B card is offered once the user comes back to the window."""
        return b"".join(self._pro_ring)

    def play_free_preview(self, pcm: bytes, seconds: float):
        """Speak `pcm` (the free tier's voice, same 24 kHz PCM16 contract) in place
        of the paid voice, then hand the paid voice back. The clip is dropped into
        the live Player, so it lands on the same device, gain and limiter the user
        is already listening to — the comparison is honest only if nothing else
        about the path changes. Best-effort: a timer failure must not strand the
        paid voice muted, so the unmute is also attempted on stop()."""
        self._preview_mute = True
        try:
            stager = getattr(self, "_stager", None)
            if stager is not None:
                stager.clear()            # drop paid audio not yet handed to Player
            self.player.clear_tts()      # drop paid audio already queued
            self.player.feed_tts_pcm16(pcm)
        except Exception:
            self._preview_mute = False
            raise
        # +0.4 s so the ring finishes draining before the paid voice resumes.
        t = threading.Timer(max(0.5, seconds) + 0.4, self._end_free_preview)
        t.daemon = True
        t.start()

    def _end_free_preview(self):
        self._preview_mute = False

    @staticmethod
    def capture_rate(dev) -> int:
        return audio_io.device_rate(dev, "input")

    def start_translator(self):
        self.translator.start()

    def start_io(self):
        # Warm the Live socket BEFORE capturing audio so the first utterance
        # does not stack the cold WS/TLS/setup handshake on top of translation.
        if not self.translator.wait_ready(timeout=6):
            raise RuntimeError(t("st_server_unreachable"))
        self.player.start()
        assert self.capture is not None  # set by _acquire_capture(), called before start_io()
        self.capture.start()

    def start(self):
        self.start_translator()
        self.start_io()

    def stop(self):
        # A preview timer that never fired must not leave the next session's paid
        # voice muted — this object is torn down, but clear the flag regardless.
        self._preview_mute = False
        _stop_all(self)
        d = getattr(self, "_sducker", None)
        if d is not None:
            d.close()
        handle = getattr(self, "_routing_handle", None)
        if handle is not None:
            try:
                sysaudio.teardown_capture_routing(handle)
            except Exception:
                pass
            self._routing_handle = None


def _swap_to_gemini(pipe, target_key, name, exc):
    """Shared mid-session engine substitution for both directions.

    A spent DashScope balance surfaces as a terminal 'arrearage'/'quota' reject.
    The server cannot see it — the Qwen key is still configured, so every voiced
    target keeps routing to Qwen — which would take the whole 29-language tier
    dark, one dead session at a time. Gemini is the 79-language catch-all, so it
    can serve whatever Qwen was serving.

    Runs on the dying translator's thread (BaseTranslator._give_up), off the audio
    path. True = handled, and the failure stays silent for the user. Never
    retried: Gemini is the last resort, so a second failure is a real outage and
    must surface."""
    if pipe._failover_done or pipe._engine == ENGINE_GEMINI:
        return False
    pipe._failover_done = True

    target = pipe.cfg[target_key]
    try:
        engine, key, model, _fallback = pipe._resolve(target, force_gemini=True)
    except Exception:
        _log.exception("failover: could not obtain a Gemini key")
        return False
    if engine != ENGINE_GEMINI or not key:
        return False

    _log.warning("engine %s gave up (%s) — failing over to Gemini", pipe._engine, exc)
    old = pipe.translator
    try:
        new = make_translator(
            pipe.cfg, target, engine=ENGINE_GEMINI, key=key, model=model,
            on_audio=pipe._tts_sink, on_text=pipe._on_text,
            on_status=pipe._on_status, name=name,
            # No on_fatal: Gemini is the last resort — a further failure must
            # reach the user instead of looping. The failover key comes from the
            # legacy (no-caps) endpoint and is always raw, so the provider is
            # passed only for symmetry — a raw key never consults it.
            key_provider=getattr(pipe._resolve, "gemini_key_provider", None),
        )
    except Exception:
        _log.exception("failover: could not build the Gemini translator")
        return False

    # No capture retarget is needed here: every engine ingests 16 kHz, which is
    # also the gate's own rate, so the already-open capture + _GatedSource carry
    # straight over to the replacement translator untouched. (This used to call
    # source.set_send_rate(16000) against a second, engine-facing rate that no
    # engine has used since OpenAI was retired.)
    #
    # Both Qwen and Gemini use the incoming adaptive playback stager. Clear its
    # provider-side pending audio at the boundary, but keep the worker alive so
    # the replacement Gemini stream gets the same catch-up behavior. Outgoing
    # pipelines intentionally have no stager.
    stager = getattr(pipe, "_stager", None)
    if stager is not None:
        try:
            stager.clear()
        except Exception:
            pass

    # And drop whatever the dead engine had already buffered — see _swap_to_cascade.
    # Qwen queues seconds ahead of the source, so without this the user goes on
    # hearing the engine that just died, reading sentences the captions have long
    # passed, while the replacement waits its turn behind the backlog.
    for player in (getattr(pipe, "player", None),
                   getattr(pipe, "monitor_player", None)):
        if player is not None:
            try:
                player.clear_tts()
            except Exception:
                pass

    from_engine = pipe._engine
    pipe._engine = ENGINE_GEMINI
    if target_key == "target_language_incoming" and stager is None:
        # An incoming pipeline can reach here with no stager (cascade paces its
        # own local synthesis and never builds one). Install one before Gemini
        # can emit audio.
        pipe._stager = AdaptivePlaybackStager(
            pipe.player, on_status=pipe._on_status, input_rate=24000)
    pipe.translator = new   # the send path indirects through pipe.translator
    new.start()
    try:
        old.stop()
    except Exception:
        pass
    pipe._on_status(t("st_engine_failover"))
    # Tell the server which engine died: the server cannot see a spent
    # DashScope balance itself (the key stays configured), so its routing
    # watcher counts these events and flips qwen_enabled off for everyone
    # once several licenses report the same dead engine.
    voxis_client.report_event_async("engine_failover", None, {
        "from": from_engine, "reason": type(exc).__name__ if exc else "",
    })
    return True


def _swap_to_cascade(pipe, target_key, name, exc):
    """Mid-session rescue for a free-tier session still inside its one-time
    15-minute Pro taste: a terminal Qwen failure would otherwise just end the
    session (2026-08-12 policy — free tier never buys a Gemini fallback).
    Swaps to cascade (the same Gemini-text + local voice engine the free
    tier's daily allowance already uses) instead, running the PREMIUM
    (Kokoro) voice tier when the target language has one — see
    local_tts.PREMIUM_VOICES — so the user doesn't drop from a paid-quality
    voice to nothing.

    THE GRANT IS SERVER-AUTHORITATIVE, not a client decision: pipe._resolve
    is asked with cascade_rescue=True, and the server (handlers/cascade.go
    CascadeRescueEligible) only answers with a cascade key while it
    independently believes Qwen is degraded — EITHER a short auto-expiring
    window (PB setting qwen_rescue_until, opened/extended by
    WatchEngineHealth's existing storm-evidence check, itself fed only by
    PAID customers' real engine_failover events, see _swap_to_gemini above)
    OR an operator's manual qwen_enabled=false as a backstop for a longer
    declared outage — AND this license still has unspent taste minutes AND
    today's daily free-cascade allowance isn't already spent (a rescue
    grant books against that SAME daily counter — not exempt from it, so a
    taste account can't ride this indefinitely) AND the mode isn't Meeting.
    This is the deliberate abuse cap: a free/taste account has no path of
    its own to open the rescue window or flip qwen_enabled — engine_failover
    is emitted ONLY by the paid path above — so it cannot grief its way into
    free premium voice by faking failures. A refusal (no key / wrong
    engine, including a healthy-Qwen "no, nothing's wrong") is silent and
    not an error: the caller's existing give-up path surfaces normally, so
    a session that gets no rescue behaves exactly as it did before this
    existed. Full design + the corrected-mid-session history: see
    .vault/cascade-rescue-taste-qwen-failure-2026-08-13.md.

    Runs on the dying translator's thread (BaseTranslator._give_up), off
    the audio path. True = handled, a status line explains it rather than
    an error reaching the user. Never retried: fires at most once per
    pipeline, same guard (_failover_done) as _swap_to_gemini — shared
    rather than duplicated because a pipeline only ever substitutes an
    engine once, regardless of which replacement it substitutes."""
    if pipe._failover_done or pipe._engine == ENGINE_CASCADE:
        return False
    pipe._failover_done = True

    target = pipe.cfg[target_key]
    # A watchdog-exhausted give-up (base_translator._WatchdogExhausted) is a
    # client-CONFIRMED dead stream (input flowing, 3 self-heal reconnects all
    # failed to restore output) rather than a bare terminal-error guess, so
    # the server grants it independently of the fleet-wide storm window
    # (CascadeRescueWindowOpen) — capped to once per license per UTC day
    # server-side (handlers/cascade.go CascadeRescueSelfVerifiedAllowed)
    # since a free/taste session otherwise controls this signal itself. See
    # .vault/cascade-rescue-taste-qwen-failure-2026-08-13.md.
    reason = "watchdog" if isinstance(exc, _WatchdogExhausted) else None
    try:
        engine, key, model, _fallback = pipe._resolve(
            target, cascade_rescue=True, reason=reason)
    except Exception:
        _log.exception("cascade rescue: resolver failed")
        return False
    if engine != ENGINE_CASCADE or not key:
        return False

    _log.warning("engine %s gave up (%s) — rescuing a taste session onto "
                "cascade", pipe._engine, exc)
    old = pipe.translator
    try:
        new = make_translator(
            pipe.cfg, target, engine=ENGINE_CASCADE, key=key, model=model,
            on_audio=pipe._tts_sink, on_text=pipe._on_text,
            on_status=pipe._on_status, name=name,
            # No on_fatal: if the cascade's own inner (Gemini-text) leg also
            # dies, that's a second, independent failure and must reach the
            # user rather than looping through further substitutions.
        )
    except Exception:
        _log.exception("cascade rescue: could not build the cascade translator")
        return False

    # Same cleanup as _swap_to_gemini: drop whatever the dead engine had
    # already buffered so the user doesn't go on hearing Qwen read sentences
    # the captions have long passed.
    stager = getattr(pipe, "_stager", None)
    if stager is not None:
        try:
            stager.clear()
        except Exception:
            pass
    for player in (getattr(pipe, "player", None),
                   getattr(pipe, "monitor_player", None)):
        if player is not None:
            try:
                player.clear_tts()
            except Exception:
                pass

    from_engine = pipe._engine
    pipe._engine = ENGINE_CASCADE
    pipe.translator = new
    new.start()
    try:
        old.stop()
    except Exception:
        pass
    pipe._on_status(t("st_cascade_rescue"))
    # Deliberately NOT "engine_failover": that event is what feeds
    # WatchEngineHealth's qwen_enabled kill-switch, which this rescue is
    # gated on. Emitting it from the free/taste path would let a free
    # account influence the very signal that decides its own eligibility —
    # a self-reinforcing loop. This name is observability-only.
    voxis_client.report_event_async("cascade_rescue_fired", None, {
        "from": from_engine, "reason": type(exc).__name__ if exc else "",
    })
    return True


class OutgoingPipeline:
    def __init__(self, cfg: dict, resolve, on_text, on_status):
        from .vad import SpeechGate
        vad_cfg = gate_params(cfg)
        mic_dev = find_device(cfg["devices"]["microphone"], "input")

        # Windows: Player targets VB-CABLE's real Input device directly (a
        # separately-addressable PortAudio device). Linux has no such
        # pre-existing virtual cable -- make_virtual_mic() creates the
        # "VoxisMic" null-sink there and returns None on Windows, where this
        # whole branch is skipped and the existing cable_out path runs
        # unchanged below. See sysaudio/linux/virtual_mic.py for why the
        # stream is pinned via an explicit one-time move rather than any
        # default-source switch (confirmed empirically: changing the default
        # source drags an already-open capture stream exactly like Faz 3's
        # sink-side finding, so it must never be touched).
        self.monitor_player = None
        # See IncomingPipeline.__init__ for why these three are declared
        # non-Optional: unset only until start() returns, read only by
        # capture-thread callbacks defined inside start() (i.e. after it set
        # them).
        self.player: Player = None  # pyright: ignore[reportAttributeAccessIssue]
        self.translator: BaseTranslator | CascadeTranslator = None  # pyright: ignore[reportAttributeAccessIssue]
        self.capture = None
        self._source: _GatedSource = None  # pyright: ignore[reportAttributeAccessIssue]
        try:
            self._mic_handle = sysaudio.make_virtual_mic()
            before_streams = sysaudio.snapshot_own_audio_streams()
            if self._mic_handle is not None:
                self.player = Player(
                    None, channels=1,
                    tts_enhance=(_premium.enhance_tts
                                 if _premium is not None else None),
                )
                moved = sysaudio.pin_newest_own_stream_to_mic(
                    before_streams, self._mic_handle)
                if moved is None:
                    raise RuntimeError(
                        "could not pin the outgoing TTS stream onto the virtual mic")
            else:
                cable_out = find_device(
                    cfg["devices"]["meeting_mic_playback"], "output")
                self.player = Player(
                    cable_out, channels=1,
                    tts_enhance=(_premium.enhance_tts
                                 if _premium is not None else None),
                )
        except Exception:
            self._teardown_resources()
            raise
        # Optional confidence monitor: the primary Player remains pinned to the
        # virtual microphone while a second Player renders the identical PCM to
        # the user's selected headphones. Construct it only after the Linux pin
        # above, otherwise the monitor could be mistaken for the new virtual-mic
        # stream. Failure is soft: the call still receives the translation.
        if cfg.get("monitor_outgoing_translation"):
            monitor = None
            try:
                monitor_out = find_device(
                    cfg["devices"].get("headphones_output", ""), "output",
                    on_status=on_status, fallback_default=True)
                monitor = Player(
                    monitor_out,
                    tts_enhance=(_premium.enhance_tts
                                 if _premium is not None else None),
                )
                monitor.tts_gain = float(cfg.get("tts_volume", 1.0))
                self.monitor_player = monitor
            except Exception:
                if monitor is not None:
                    try:
                        monitor.stop()
                    except Exception:
                        pass
                self.monitor_player = None
                _log.exception("outgoing confidence monitor unavailable")
        try:
            self._engine, _key, _model, _fallback = resolve(cfg["target_language_outgoing"])
        except Exception:
            self._teardown_resources()
            raise
        self.cfg = cfg
        self._resolve = resolve
        self._on_text = on_text
        self._on_status = on_status
        self._failover_done = False
        # Outgoing feeds the virtual mic directly — no SyncStager on this leg.
        self._tts_sink = self._feed_translated_audio
        try:
            self.translator = make_translator(
                cfg, cfg["target_language_outgoing"], engine=self._engine, key=_key,
                model=_model, on_audio=self._tts_sink, on_text=on_text,
                on_status=on_status, name=t("name_out"),
                # See the matching comment in IncomingPipeline._build: Gemini
                # failover is paid-only.
                on_fatal=self._failover_to_gemini if cfg.get("_paid_customer") else None,
                key_provider=getattr(resolve, "gemini_key_provider", None),
                beta_active=getattr(resolve, "beta_active", False),
                # The voice the OTHER party hears as the user — its own setting,
                # independent of the incoming leg's.
                voice=resolve_voice(self._engine,
                                    cfg.get("voice_gender_outgoing", "auto")),
                fallback=_fallback,
            )
        except Exception:
            self._teardown_resources()
            raise
        self.input_level = 0.0
        # Capture opens the mic InputStream at construction. Guard the capture +
        # gate acquisition so a mid-init failure releases the mic stream and the
        # already-open Player/translator instead of leaking them when
        # ModeController.start discards the half-built pipeline.
        try:
            self.capture = Capture(mic_dev, self._on_mic)
            self._source = _GatedSource(
                # Indirect through self so a mid-session engine swap
                # (_failover_to_gemini) redirects the mic without rebuilding it.
                self.capture.rate, SpeechGate(**vad_cfg),
                lambda pcm: self.translator.send_pcm16(pcm),
                smart=not stream_gated(cfg),
            )
        except Exception:
            self._teardown_resources()
            raise

    def _teardown_resources(self):
        """Best-effort release of whatever was acquired; safe with partial init."""
        if self._source is not None:
            self._source.closed = True
        for comp in (self.capture, getattr(self, "player", None),
                     getattr(self, "monitor_player", None),
                     getattr(self, "translator", None)):
            if comp is not None:
                try:
                    comp.stop()
                except Exception:
                    pass
        handle = getattr(self, "_mic_handle", None)
        if handle is not None:
            try:
                sysaudio.teardown_virtual_mic(handle)
            except Exception:
                pass
            self._mic_handle = None

    def _on_mic(self, c: np.ndarray):
        mono = c.mean(axis=1) if getattr(c, "ndim", 1) > 1 else c
        self.input_level = _rms_level(self.input_level, mono)
        self._source.feed(c)

    def _feed_translated_audio(self, data: bytes) -> None:
        """Send outgoing translation to the call and optional local monitor."""
        self.player.feed_tts_pcm16(data)
        if self.monitor_player is not None:
            self.monitor_player.feed_tts_pcm16(data)

    def start_translator(self):
        self.translator.start()

    def start_io(self):
        if not self.translator.wait_ready(timeout=6):
            raise RuntimeError(t("st_server_unreachable"))
        self.player.start()
        if self.monitor_player is not None:
            try:
                self.monitor_player.start()
            except Exception:
                _log.exception("could not start outgoing confidence monitor")
                try:
                    self.monitor_player.stop()
                except Exception:
                    pass
                self.monitor_player = None
        assert self.capture is not None  # set earlier in start(), before start_io()
        self.capture.start()

    def start(self):
        self.start_translator()
        self.start_io()

    def _failover_to_gemini(self, exc) -> bool:
        return _swap_to_gemini(self, "target_language_outgoing", t("name_out"), exc)

    def stop(self):
        _stop_all(self)
        handle = getattr(self, "_mic_handle", None)
        if handle is not None:
            try:
                sysaudio.teardown_virtual_mic(handle)
            except Exception:
                pass
            self._mic_handle = None


def _stop_all(pipeline):
    """Stops all components independently so a failure in one does not block the
    others. Components may be None if init failed mid-way before acquiring them."""
    src = getattr(pipeline, "_source", None)
    if src is not None:
        src.closed = True
    fns = []
    for attr in ("capture", "_stager", "player", "monitor_player", "translator",
                 "_recorder", "_spk_tracker"):
        comp = getattr(pipeline, attr, None)
        if comp is not None:
            fns.append(comp.stop)
    for fn in fns:
        try:
            fn()
        except Exception:
            pass
    # Join the translator thread so its receiver cannot deliver a late
    # on_text/on_audio into the NEXT session's freshly-cleared transcript
    # buffers (the 'ghost turn' desync — audit P2-4/P2-7). stop() already set
    # _stopping and nudged the event loop, so the sender wakes within ~0.5 s and
    # the thread converges well inside this bound; the timeout only guards the
    # rare mid-backoff case (during which no receiver is emitting anyway).
    tr = getattr(pipeline, "translator", None)
    if tr is not None and hasattr(tr, "join") and hasattr(tr, "is_alive"):
        try:
            if tr.is_alive():
                tr.join(timeout=2.0)
        except Exception:
            pass


def _event_error_class(exc: Exception) -> str:
    """Coarse, PII-free label for a session-start failure, for the activation
    funnel. Never carries the raw message (which may hold device names/paths).

    The `other` bucket used to swallow 82 of 143 recorded start failures, i.e.
    the majority of the errors we most needed to name. Existing labels are kept
    verbatim so historical rows stay comparable; the fallback now appends the
    exception's CLASS name (a type, never a message — no device names, no paths,
    no user text), so an unclassified failure is at least identifiable.

    Keyword matching is deliberately secondary to type matching: several of our
    own RuntimeErrors carry a LOCALIZED message, so an English keyword would
    only ever match for English users."""
    msg = str(exc)
    low = msg.lower()
    if "-9999" in msg or "PaError" in msg or "host error" in msg or "host API" in msg:
        return "audio_device"
    if isinstance(exc, ImportError):
        return "os_import"
    if "timeout" in low or "ready" in low:
        return "translator_timeout"
    # Ordered before the generic OSError arm: a socket/DNS/TLS failure IS an
    # OSError, and calling that "os_import" is what made the label useless.
    if any(k in low for k in ("getaddrinfo", "connection", "unreachable",
                              "ssl", "certificate", "network", "resolve host")):
        return "network"
    if any(k in low for k in ("api key", "api_key", "unauthorized", "401",
                              "403", "permission")):
        return "auth_key"
    if "quota" in low or "402" in low:
        return "quota"
    if any(k in low for k in ("cable", "virtual mic", "virtual microphone")):
        return "cable"
    if "device" in low or "not found" in low or "no default" in low:
        return "no_device"
    if "heartbeat" in low:
        return "busy_restart"
    if isinstance(exc, OSError):
        return "os_error"
    return "other:" + type(exc).__name__


class ModeController:
    """Single-active-mode controller (video | meeting). start() implicitly stops
    any current session first."""

    # Usage report interval. Smaller = less time lost when the process is
    # killed abruptly (Ctrl+C, crash, network drop).
    HEARTBEAT_SECONDS: float = 6.0

    # No-input notice: how long a session may run without ANY audio reaching the
    # capture before we say so out loud. Measured motivation: 40% of all sessions
    # end under 30 s and 59% under a minute, and a short session is followed by
    # another attempt 14 s later 71% of the time — people are not losing
    # interest, they are staring at a silent app. The input meter already shows
    # "waiting for system audio", but it is a small badge next to a video the
    # user is watching full-screen, so nobody reads it.
    #
    # Threshold matches the UI meter's own "has signal" cut (index.html
    # hasInputSignal, level > 0.02) so the badge and this notice can never
    # disagree about whether audio is arriving.
    NO_INPUT_WARN_SECONDS: float = 12.0
    INPUT_SILENT_LEVEL: float = 0.02

    def __init__(self, cfg: dict, api_key: str | None, on_text, on_status,
                 on_usage_reported=None, on_quota_exceeded=None,
                 on_session_failed=None, on_speaker=None):
        self.cfg = cfg
        self.api_key = api_key       # legacy field; key resolution now via self.resolve
        # callable(target)->(engine, key, model, fallback); set by the bridge.
        # webui._build_engine_resolver() also hangs ad-hoc `beta_active` /
        # `gemini_key_provider` attributes off some of its returned callables
        # (read defensively via getattr elsewhere), which don't fit a Callable
        # type — hence the plain signature here rather than a stricter Protocol.
        self.resolve: Callable[..., tuple] | None = None
        self.on_text = on_text
        self.on_status = on_status
        # Speaker-change events (incoming direction) from the local tracker;
        # None disables labeling entirely.
        self.on_speaker = on_speaker
        self.on_usage_reported = on_usage_reported or (lambda: None)
        # Fired (at most once per session) when the server reports the license is
        # exhausted via a 402 on /usage/report. The server cannot stop a running
        # Live session, so the bridge wires this to its session teardown.
        self.on_quota_exceeded = on_quota_exceeded or (lambda: None)
        # Fired (at most once per session) when a translator thread dies
        # unexpectedly mid-session. Billing already stops via _is_session_live,
        # but capture/ducking/endpoint redirection stay live — the bridge wires
        # this to tear the session down.
        self.on_session_failed = on_session_failed or (lambda: None)
        self._quota_exhausted = threading.Event()
        self._session_failed = threading.Event()
        self._capture_dead_notified = False
        self._no_input_notified = False
        self._pipelines: list = []
        # backlog/skipped/sped watermarks per stager id, so the heartbeat only
        # logs playback health when catch-up compression or a stale-audio trim
        # actually happened — not every 6s of a perfectly healthy 1.0x session.
        # Survives the session so the post-session A/B card can replay it.
        self._last_pro_pcm: bytes = b""
        self.mode: str | None = None
        self._session_id: str | None = None
        self._session_start: float | None = None
        self._session_mode: str | None = None
        # _last_report is the watermark for "minutes already billed". Every read
        # AND write goes through _heartbeat_lock so the periodic heartbeat and
        # the stop() tail can never both consume the same interval (double-count).
        self._last_report: float | None = None
        self._heartbeat_lock = threading.Lock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def _switch_defaults(self, mode: str):
        """Swap Windows default endpoints when required and remember the prior
        selection so stop() can restore it.

        Driverless mode leaves the output device untouched (the user keeps
        hearing audio on their normal device; loopback reads it). Meeting mode
        still flips the default microphone to the virtual cable since the
        outbound direction needs a driver."""
        # Windows-only default-endpoint switching (vbcable/meeting mode); no-op
        # elsewhere. Deliberately NOT gated on is_supported() -- Linux's Faz 3
        # driverless-equivalent path is supported without this (see
        # sysaudio.supports_endpoints), and never touches the default sink.
        if not sysaudio.supports_endpoints():
            return
        win_audio = sysaudio.endpoints()
        from .config import save_config

        driverless = self.cfg.get("capture_backend", "driverless") != "vbcable"
        saved = self.cfg.get("_pending_default_restore") or {}

        if not driverless:
            if "output" not in saved:
                out_id, out_name = win_audio.get_default("output")
                if "CABLE" in out_name or "VB-Audio" in out_name:
                    # Only resolve when a real device name is configured; an empty
                    # headphones_output must not be matched to an arbitrary endpoint
                    # (find_endpoint_id now rejects blanks), so keep the current id.
                    hp = (self.cfg.get("devices", {}).get("headphones_output") or "").strip()
                    if hp:
                        out_id = win_audio.find_endpoint_id(hp)
                saved["output"] = out_id
            win_audio.set_default(
                win_audio.find_endpoint_id("CABLE Input (VB-Audio Virtual Cable)"))
            self.on_status(t("st_redirected"))

        if mode == "meeting" and getattr(self, "_outgoing_ok", False):
            try:
                if "input" not in saved:
                    in_id, in_name = win_audio.get_default("input")
                    if not ("CABLE" in in_name or "VB-Audio" in in_name):
                        saved["input"] = in_id
                win_audio.set_default(
                    win_audio.find_endpoint_id(self.cfg["devices"]["meeting_virtual_mic"]))
            except Exception:
                self.on_status(t("st_virtual_mic_missing",
                                 dev=self.cfg["devices"]["meeting_virtual_mic"]))

        if saved:
            self.cfg["_pending_default_restore"] = saved
            save_config(self.cfg)

    def _restore_defaults(self):
        # Windows-only endpoint restore; no-op elsewhere so stop()/start()
        # (which always calls stop() first) never crash on Linux. See
        # _switch_defaults for why this checks supports_endpoints(), not
        # is_supported().
        if not sysaudio.supports_endpoints():
            return
        win_audio = sysaudio.endpoints()
        from .config import save_config

        saved = self.cfg.get("_pending_default_restore")
        if not saved:
            return
        try:
            win_audio.restore(saved)
        except Exception as e:
            # Restore failed (transient COM/device error). KEEP the snapshot so the
            # next stop() or app launch retries — clearing it here would strand the
            # default endpoint on the virtual cable with no record to recover from.
            self.on_status(t("st_restore_fail", e=e))
            return
        self.on_status(t("st_restored"))
        self.cfg["_pending_default_restore"] = None
        save_config(self.cfg)

    def _text_sink(self, leg: str):
        """Bind the caption callback to a conversation side.

        Both meeting pipelines feed the same sink, so without this tag the two
        translations interleave into one caption line and land in the transcript
        indistinguishable from each other. Falls back to the untagged call for a
        consumer that predates the leg argument (tests with a 2-arg stub)."""
        def sink(direction, text):
            try:
                self.on_text(direction, text, leg)
            except TypeError:
                self.on_text(direction, text)
        return sink

    def _build(self, mode: str) -> list:
        resolve = self.resolve
        session_dir = getattr(self, "_session_dir_out", None)
        if mode == "video":
            return [IncomingPipeline(self.cfg, resolve, mode,
                                     self._text_sink("incoming"),
                                     self.on_status, session_dir=session_dir,
                                     on_speaker=self.on_speaker)]
        if mode == "meeting":
            pipes: list[IncomingPipeline | OutgoingPipeline] = [
                IncomingPipeline(self.cfg, resolve, "meeting",
                                  self._text_sink("incoming"), self.on_status,
                                  session_dir=session_dir,
                                  on_speaker=self.on_speaker)]
            try:
                # Outbound direction requires a virtual microphone driver. If
                # none is installed, the meeting gracefully falls back to
                # listen-only.
                pipes.append(OutgoingPipeline(self.cfg, resolve,
                                              self._text_sink("outgoing"),
                                              self.on_status))
                self._outgoing_ok = True
            except Exception:
                self._outgoing_ok = False
                self.on_status(t("st_meeting_listen_only"))
            return pipes
        raise ValueError(f"Unknown mode: {mode}")

    def _is_session_live(self) -> bool:
        """True only while at least one pipeline is actively translating.

        Gates billing on real liveness: the translator must have completed its
        warmup handshake (_ready) and not be shutting down (_stopping). Outage /
        reconnect-storm time, where the socket is down and no audio flows, is NOT
        accrued — the user is not getting service, so they are not billed for it.

        NOTE: _ready is cleared by the translator on every reconnect/backoff
        iteration, so ordinary outages stop accrual within one heartbeat. The
        remaining hole — a silently hung socket that never raises — is closed
        by the translators' stall watchdog (_STALL_ROTATE_SECONDS): sent audio
        with zero server events forces a rotation, whose gap clears _ready.
        """
        for p in self._pipelines:
            # A capture backend that died mid-session (device unplug, exclusive-
            # mode grab, sleep/resume) means no audio is flowing for this pipeline
            # — it is not providing service, so don't accrue billing for it.
            cap = getattr(p, "capture", None)
            if cap is not None and getattr(cap, "failed", False):
                continue
            tr = getattr(p, "translator", None)
            if tr is None:
                continue
            ready = getattr(tr, "_ready", None)
            stopping = getattr(tr, "_stopping", None)
            live = (ready is None or ready.is_set()) and \
                   (stopping is None or not stopping.is_set())
            if live and tr.is_alive():
                return True
        return False

    def translated_audio_seconds(self) -> float:
        """Seconds of translated speech produced so far this session.

        Summed across pipelines (a meeting produces on both legs). Cheap enough
        to sample from the caption path — it is a float read, no lock."""
        total = 0.0
        for p in self._pipelines:
            total += float(getattr(p, "_tts_seconds", 0.0) or 0.0)
        return total

    def _consume_minutes(self, accrue: bool) -> tuple[str | None, float, str | None]:
        """Atomic get-and-reset of billable minutes since the last watermark.

        Advances _last_report to now and returns (session_id, delta_minutes,
        source) under _heartbeat_lock so the heartbeat and the stop() tail can
        never bill the same interval twice. When accrue is False the watermark is
        still advanced (so outage time is skipped, not deferred) but delta is
        zeroed — the elapsed wall-clock is intentionally dropped, not billed."""
        with self._heartbeat_lock:
            sid = self._session_id
            last = self._last_report
            smode = self._session_mode
            if not sid or last is None:
                return None, 0.0, None
            now = time.monotonic()
            self._last_report = now
            delta = (now - last) / 60.0 if accrue else 0.0
            if delta < 0:
                delta = 0.0
            source = "video" if smode == "video" else "meeting_incoming"
            return sid, delta, source

    def _heartbeat_loop(self):
        """Periodic usage reporter. Consumes the delta since the last beat and
        signals the UI to refresh the quota badge. on_usage_reported is fanned
        out to its own thread so a slow UI callback cannot stall the heartbeat
        cadence (and thus skew the next interval's billable delta)."""
        while not self._heartbeat_stop.wait(self.HEARTBEAT_SECONDS):
            sid, delta, source = self._consume_minutes(accrue=self._is_session_live())
            self._maybe_warn_capture_dead()
            self._maybe_warn_no_input()
            self._maybe_handle_translator_dead()
            self._log_playback_health()
            if not sid:
                continue
            assert source is not None  # _consume_minutes: sid and source are set together
            if delta > 0:
                # Same client clamp the stop() tail applies: one interval can never
                # legitimately exceed a heartbeat (+ bounded slack). On sleep/resume
                # the monotonic clock jumps while capture may not flag failed, which
                # would otherwise bill the whole wall-clock gap as one delta. Cap only
                # the REPORTED value — the watermark already advanced past the excess
                # in _consume_minutes, so the surplus is dropped, not deferred.
                max_beat = (self.HEARTBEAT_SECONDS + 2.0) / 60.0
                voxis_client.report_usage_async(
                    sid, min(delta, max_beat), source, self.current_engine() or "gemini",
                    on_quota_exceeded=self._fire_quota_exceeded)
            self._dispatch_usage_reported()

    def _log_playback_health(self):
        """Log translated-speech pacing stats once per heartbeat, but only when
        catch-up compression or a stale-audio trim actually occurred since the
        last check. A field report of choppy/harsh translated audio otherwise
        has no telemetry to root-cause against — the stager tracks exactly
        this (speed/skipped_s/sped_s), it just was not surfaced to the log.

        Qwen's duplicate-audio detector rides along: it counts server deltas that
        repeat or overlap the previous one, which is the other way translated
        audio turns choppy, and until now nothing but a unit test ever read that
        counter. It is 0 on every other engine.

        The watermark lives ON the stager rather than in a dict here: keyed by
        id(stager) it could collide after a stager was collected and a new one
        landed at the same address, silently suppressing the next real event."""
        for p in self._pipelines:
            stager = getattr(p, "_stager", None)
            if stager is None:
                continue
            skipped, sped = stager.skipped_s, stager.sped_s
            prev_skipped, prev_sped = stager.logged_watermark
            backlog = stager.backlog_s
            dup = int(getattr(getattr(p, "translator", None),
                              "_dup_audio_count", 0) or 0)
            prev_dup = stager.logged_dup_audio
            if (skipped > prev_skipped or sped > prev_sped or dup > prev_dup
                    or backlog >= 2.0):
                _log.info(
                    "playback health: engine=%s backlog=%.1fs speed=%.2fx "
                    "compressed_total=%.1fs trimmed_total=%.1fs dup_audio=%d",
                    getattr(p, "_engine", "?"), backlog, stager.speed, sped,
                    skipped, dup)
            stager.logged_watermark = (skipped, sped)
            stager.logged_dup_audio = dup

    def _maybe_warn_capture_dead(self):
        """Once per session, if a capture backend died mid-session, surface it so a
        green badge + silent transcript don't read as 'working'. Billing already
        stops via _is_session_live; this is the user-facing half."""
        if self._capture_dead_notified:
            return
        for p in self._pipelines:
            cap = getattr(p, "capture", None)
            if cap is not None and getattr(cap, "failed", False):
                self._capture_dead_notified = True
                voxis_client.report_event_async("capture_lost", self._session_id,
                                                {"mode": self._session_mode})
                try:
                    self.on_status(t("st_capture_lost"))
                except Exception:
                    pass
                return

    def _report_session_end(self, reason: str):
        """Close the activation funnel's open end: why a LIVE session ended, and
        whether the user ever heard a translation.

        The funnel used to stop at session_live, so a session that started fine
        and was abandoned 20 seconds later was indistinguishable from one that
        ran to completion — and 40% of all sessions end under 30 s. Four fields
        answer the questions that guesswork could not:
          reason      user_stop | restart | quota | error | capture_lost | app_close
          seconds     how long it actually ran
          first_audio the measured first-speech→first-translated-audio span, which
                      RTTEstimator has always computed for the UI but never
                      reported; None means the user never heard one word
          speech_seen whether any speech ever reached us, i.e. "nothing was
                      playing / they spoke into their mic" vs "audio flowed but
                      the translation didn't"

        PII-free by construction: durations, booleans and a fixed label set.
        Fires only for a session that actually went live (a start failure already
        reports session_error), and never raises into teardown."""
        try:
            sid = self._session_id
            started = self._session_start
            if not sid or started is None:
                return
            if self._quota_exhausted.is_set():
                reason = "quota"
            elif self._session_failed.is_set():
                reason = "error"
            elif self._capture_dead_notified:
                reason = "capture_lost"
            inc = self.incoming()
            peak = round(float(getattr(inc, "peak_input_level", 0.0)), 3) if inc else 0.0
            rtt = getattr(inc, "_rtt", None) if inc else None
            voxis_client.report_event_async("session_end", sid, {
                "mode": self._session_mode or "",
                "reason": reason,
                "seconds": int(max(0.0, time.monotonic() - started)),
                "first_audio_s": rtt.first_audio_seconds if rtt is not None else None,
                "speech_seen": bool(rtt.speech_seen) if rtt is not None else False,
                "peak_level": peak,
                "engine": self.current_engine() or "",
            })
        except Exception:
            _log.debug("session_end telemetry failed", exc_info=True)

    def _maybe_warn_no_input(self):
        """Once per session, if no audio at all has reached the capture after
        NO_INPUT_WARN_SECONDS, say so and name the two things that actually cause
        it. Until now the app stayed completely silent in this state: a user who
        had nothing playing, or who was speaking into their microphone expecting
        Video mode to translate it, got no signal, no caption and no explanation.

        VIDEO MODE ONLY, and not as a preference: on the incoming leg of a
        meeting, total silence is the normal state of a call nobody is talking in
        yet (a muted remote party is digital zero), so the same notice there
        would cry wolf during real calls. Video/Game is 95% of sessions.

        Billing is untouched — this is a status line, nothing else. It is NOT the
        idle-pause machinery that was removed by owner decision on 2026-07-29:
        accrual still runs on wall clock, and no session is ever paused or
        stopped from here."""
        if self._no_input_notified or self._session_mode != "video":
            return
        started = self._session_start
        if started is None or time.monotonic() - started < self.NO_INPUT_WARN_SECONDS:
            return
        inc = self.incoming()
        if inc is None:
            return
        # Peak, not the instantaneous meter: the meter's slow release can dip to
        # ~0 in a pause, but a session that has heard anything at all keeps a peak.
        if (inc.peak_input_level > self.INPUT_SILENT_LEVEL
                or (getattr(inc, "_rtt", None) is not None and inc._rtt.speech_seen)):
            self._no_input_notified = True   # audio arrived — never ask again
            return
        self._no_input_notified = True
        try:
            self.on_status(t("st_no_input_audio"))
        except Exception:
            pass

    def _maybe_handle_translator_dead(self):
        """Tear the session down (once) if a translator thread died mid-session.

        A translator that completed warmup (_ready set) and is no longer alive,
        while not intentionally stopping (_stopping), has crashed out of its run
        loop — capture, ducking and the endpoint redirection are still live and
        the badge is a false green, but no translation is happening. We only fire
        when the whole session is no longer live (_is_session_live False), so a
        meeting whose outgoing leg died but incoming still works keeps running.
        A transient reconnect keeps the thread alive, so it is not flagged.

        bridge.stop() dispatches teardown to its own thread, so calling
        on_session_failed inline from the heartbeat thread cannot self-join."""
        if self._session_failed.is_set() or not self.mode:
            return
        any_dead = False
        for p in self._pipelines:
            tr = getattr(p, "translator", None)
            if tr is None:
                continue
            stopping = getattr(tr, "_stopping", None)
            if stopping is not None and stopping.is_set():
                continue
            ready = getattr(tr, "_ready", None)
            if (ready is None or ready.is_set()) and not tr.is_alive():
                any_dead = True
        if any_dead and not self._is_session_live():
            self._session_failed.set()
            try:
                self.on_session_failed()
            except Exception:
                pass

    def _fire_quota_exceeded(self):
        """Server signaled the license is exhausted (402). Fire-once per session:
        several in-flight heartbeat reports can each receive the 402, but only the
        first should trigger teardown. Reset in start()."""
        if self._quota_exhausted.is_set():
            return
        self._quota_exhausted.set()
        try:
            self.on_quota_exceeded()
        except Exception:
            pass

    def _dispatch_usage_reported(self):
        """Run the UI quota-refresh callback off the heartbeat thread."""
        threading.Thread(
            target=self._safe_usage_reported, daemon=True, name="voxis-usage-cb"
        ).start()

    def _safe_usage_reported(self):
        try:
            self.on_usage_reported()
        except Exception:
            pass

    def start(self, mode: str, session_dir: str | None = None, paid: bool = False,
             taste_rescue: bool = False):
        # "restart", not a user stop: this stop() is the implicit teardown of a
        # session the user is replacing (a mode switch, or a settings change that
        # has to re-open the engine handshake). Labeling it keeps config churn
        # out of the give-up numbers.
        self.stop(reason="restart")
        if self.resolve is None:
            raise RuntimeError(t("st_no_key"))
        # No native OS audio backend on this platform (e.g. a Linux box without
        # PipeWire/Pulse tooling on PATH, or any other unsupported OS). Decline
        # the session with a friendly status instead of crashing deep in the
        # capture build. Windows and PipeWire-equipped Linux are supported, so
        # this is a no-op there.
        if not sysaudio.is_supported():
            self.on_status(t("st_no_audio_backend"))
            return False
        # Per-session output folder decided by the caller (webui) so the recorder's
        # WAVs land beside the transcript JSON in one self-contained folder.
        self._session_dir_out = session_dir
        # Premium auto-routing: when a virtual cable is present, run the
        # music-preserving spatial (vbcable) path; otherwise driverless. The user
        # never chooses. No-op on the OSS build (premium absent → stays driverless).
        #
        # MEETING IS EXEMPT, and it is not a preference: the two directions would
        # share one cable. The outgoing leg writes the translated voice into CABLE
        # Input (OutgoingPipeline), and the vbcable capture path listens on CABLE
        # Output — the same cable read back — so Voxis hears its own outgoing
        # translation as if the other party had spoken it and translates it again
        # into the user's language. Reported from the field: a Meeting user heard
        # a phantom third voice in their own language. Driverless capture excludes
        # our own process at the OS level, so the loop cannot form there; the cable
        # then carries the outgoing direction only.
        if mode != "meeting" and _premium is not None and hasattr(
                _premium, "resolve_capture_backend"):
            try:
                self.cfg["capture_backend"] = _premium.resolve_capture_backend(self.cfg)
            except Exception:
                pass
        elif mode == "meeting":
            self.cfg["capture_backend"] = "driverless"
        # Read by engines.make_translator's Qwen branch: a paying customer's
        # session gets a 1-strike reconnect budget instead of Qwen's normal 8,
        # so any dropped connection hands off to Gemini immediately rather
        # than riding out a flaky free engine (see engines.py for why).
        self.cfg["_paid_customer"] = bool(paid)
        # Free/taste session eligible for the mid-session Qwen-failure cascade
        # rescue (see _swap_to_cascade below) — a separate flag rather than an
        # else-branch off _paid_customer so the two perks (Gemini failover vs.
        # cascade rescue) stay independently auditable. In practice mutually
        # exclusive: _is_paid() and _taste_active() can't both be true for the
        # same license (webui._taste_active).
        self.cfg["_taste_rescue_eligible"] = bool(taste_rescue)
        # Correlation id shared by this session's funnel milestones. Generated
        # before the retry loop so session_start/live/error all carry the same id.
        sid = uuid.uuid4().hex[:16]
        voxis_client.report_event_async("session_start", sid, {"mode": mode})
        last_err: Exception | None = None
        for attempt in range(3):
            # Stale PortAudio device list is a known cause of WDM-KS -9999.
            audio_io.refresh()
            pipes: list = []
            try:
                pipes = self._build(mode)
                # Two-phase start so meeting mode's two Live sessions warm up
                # concurrently: kick off every connection first, then wait on
                # them — the handshakes overlap, so total ≈ max, not sum.
                for p in pipes:
                    p.start_translator()
                for p in pipes:
                    p.start_io()
                self._pipelines = pipes
                self.mode = mode
                # Client-generated session_id is a correlation tag ONLY: the
                # server must derive billable minutes from server-observed
                # session state (connect/disconnect, key issuance), never trust
                # this id or the reported delta as authoritative. See _consume /
                # tail report for the matching client-side sanity clamp.
                self._session_id = sid
                self._session_start = time.monotonic()
                self._last_report = self._session_start
                self._session_mode = mode
                # New session — re-arm the one-shot quota cutoff + capture-death
                # notice + translator-death teardown.
                self._quota_exhausted.clear()
                self._session_failed.clear()
                self._capture_dead_notified = False
                self._no_input_notified = False
                # Never run two heartbeats at once: a prior thread that survived
                # stop()'s bounded join would race this one on _last_report and
                # double-bill. Refuse to start until it is truly gone.
                prior = self._heartbeat_thread
                if prior is not None and prior.is_alive():
                    raise RuntimeError("previous heartbeat thread still running")
                self._heartbeat_stop = threading.Event()
                self._heartbeat_thread = threading.Thread(
                    target=self._heartbeat_loop, daemon=True, name="voxis-heartbeat"
                )
                self._heartbeat_thread.start()
                try:
                    self._switch_defaults(mode)
                except Exception as e:
                    self.on_status(t("st_autoswitch_fail", e=e))
                # AFTER the default endpoint has been flipped, never before: the
                # mirror follows whichever endpoint the user's volume keys reach,
                # and in vbcable mode that only becomes the cable here. Starting it
                # earlier latched it onto the headphones and the keys did nothing —
                # which is exactly the bug this fixes.
                self._start_volume_mirror()
                self.on_status(t("st_mode_started", mode=mode))
                meta = {
                    "mode": mode,
                    "backend": self.cfg.get("capture_backend", "driverless"),
                    "engine": self.current_engine() or "",
                }
                if mode == "meeting":
                    # Whether the OUTGOING leg actually came up (it needs a virtual
                    # mic; without one the meeting degrades to listen-only). Pure
                    # telemetry: it tells the cost dashboard how many meeting
                    # minutes really ran two concurrent engines. Deliberately NOT
                    # folded into the heartbeat's `source` — the server keys its
                    # billing multiplier off that exact string
                    # (handlers/usage.go billableMinutes), so changing it would
                    # move money, and meeting is intentionally billed 1:1.
                    meta["two_way"] = bool(getattr(self, "_outgoing_ok", False))
                voxis_client.report_event_async("session_live", sid, meta)
                return True
            except Exception as e:
                for p in pipes:
                    try:
                        p.stop()
                    except Exception:
                        pass
                last_err = e
                msg = str(e)
                if attempt == 2 or not ("-9999" in msg or "PaError" in msg or "host error" in msg):
                    voxis_client.report_event_async("session_error", sid, {
                        "mode": mode, "reason": _event_error_class(e),
                        "attempt": attempt + 1,
                    })
                    raise
                if attempt == 1:
                    # Last attempt: drop the low-latency request entirely.
                    audio_io.LATENCY = None
                self.on_status(t("st_audio_retry", n=attempt + 1))
                time.sleep(0.6)
        voxis_client.report_event_async("session_error", sid, {
            "mode": mode, "reason": _event_error_class(last_err) if last_err else "other",
            "attempt": 3,
        })
        if last_err is not None:
            raise last_err
        raise RuntimeError("audio retry loop exhausted without capturing an error")

    def set_tts_volume(self, volume: float):
        self.cfg["tts_volume"] = volume
        for p in self._pipelines:
            if isinstance(p, IncomingPipeline):
                p.player.tts_gain = volume
            elif isinstance(p, OutgoingPipeline) and p.monitor_player is not None:
                p.monitor_player.tts_gain = volume

    def set_duck_gain(self, gain: float):
        self.cfg["duck_gain"] = gain
        for p in self._pipelines:
            if isinstance(p, IncomingPipeline) and hasattr(p, "_duck_gain"):
                p._duck_gain = gain

    def set_audio_mode(self, mode: str):
        self.cfg["original_audio"] = mode
        for p in self._pipelines:
            if isinstance(p, IncomingPipeline) and hasattr(p, "_original_mode"):
                p._original_mode = mode

    def incoming(self) -> "IncomingPipeline | None":
        """The live incoming pipeline, if a session is running. The free-voice
        preview borrows its Player so the comparison plays on exactly the path
        the user is already hearing."""
        for p in self._pipelines:
            if isinstance(p, IncomingPipeline):
                return p
        return None

    def _start_volume_mirror(self):
        """vbcable only: the session has just made the CABLE the default endpoint,
        so the volume keys, the OSD and the mute key now act on the cable — not on
        the headphones Voxis plays to. Mirror the cable's level onto our output so
        the user's own volume control reaches what they actually hear.

        Driverless never needs this: there the default endpoint IS our output
        device, so Windows already attenuates us — mirroring would attenuate twice.
        Best-effort; a missing mirror is a nuisance, a crashed session is not.

        Also neutralizes the physical output device's OWN endpoint level (see
        endpoint_volume.OutputLevelNeutralizer) so that mirrored CABLE level is
        the only attenuator in the chain — otherwise a headphone device left
        below 100% from before the switch silently caps the output under
        whatever the mirror computes, with no way back to it via the keys."""
        self._vol_mirror = None
        self._out_neutralizer = None
        if self.cfg.get("capture_backend", "driverless") != "vbcable":
            return
        inc = self.incoming()
        if inc is None:
            return
        try:
            from .endpoint_volume import (
                EndpointVolumeMirror,
                OutputLevelNeutralizer,
            )
            out_name = getattr(inc, "_out_device_name", "")
            if out_name:
                self._out_neutralizer = OutputLevelNeutralizer(out_name)
                self._out_neutralizer.apply()
            self._vol_mirror = EndpointVolumeMirror(inc.player)
            self._vol_mirror.start()
        except Exception:
            _log.info("endpoint volume mirror not started", exc_info=True)

    def _stop_volume_mirror(self):
        m = getattr(self, "_vol_mirror", None)
        if m is not None:
            m.stop()          # also hands the player's gain back at full scale
            self._vol_mirror = None
        n = getattr(self, "_out_neutralizer", None)
        if n is not None:
            n.restore()
            self._out_neutralizer = None

    def recent_pro_pcm(self) -> bytes:
        """The last seconds the paid voice spoke — during the session from the live
        ring, after it from the snapshot taken at stop()."""
        inc = self.incoming()
        if inc is not None:
            live = inc.recent_pro_pcm()
            if live:
                return live
        return getattr(self, "_last_pro_pcm", b"")

    # ---------- UI telemetry ----------
    def current_level(self) -> float:
        """Smoothed input level (0..1) across active pipelines, for the UI meter."""
        lv = 0.0
        for p in self._pipelines:
            lv = max(lv, float(getattr(p, "input_level", 0.0)))
        return round(lv, 3)

    def current_latency(self) -> float | None:
        """Estimated ear-voice span (seconds) from the incoming pipeline, or None
        until enough onsets have been measured."""
        for p in self._pipelines:
            rtt = getattr(getattr(p, "_rtt", None), "first_audio_seconds", None)
            if rtt:
                return round(rtt, 2)
        return None

    def current_engine(self):
        """Engine of the active incoming pipeline (for the UI readout), or None."""
        for p in self._pipelines:
            e = getattr(p, "_engine", None)
            if e:
                return e
        return None

    def current_playback_backlog(self) -> float:
        """Seconds of translated audio queued but not yet audible, from the
        incoming pipeline's adaptive stager. 0.0 when idle or engine has no
        stager (cascade paces its own local synthesis and never builds one)."""
        stager = getattr(self.incoming(), "_stager", None)
        if stager is None:
            return 0.0
        try:
            return round(float(stager.backlog_s), 2)
        except Exception:
            return 0.0

    def is_playing(self) -> bool:
        """True while translated TTS is actively playing back."""
        return any(getattr(getattr(p, "player", None), "tts_active", False)
                   for p in self._pipelines)

    def stop(self, reason: str = "user_stop"):
        """Tear the session down. `reason` is telemetry only — it never changes
        what is billed or restored. start() passes "restart" so a config change
        that re-opens the session (language, quality, voice, terms) is
        distinguishable from a user who actually pressed Stop; without that,
        settings fiddling and genuine give-ups look identical in the funnel."""
        # Stop and JOIN the heartbeat FIRST so _last_report has exactly one
        # remaining reader. With the heartbeat gone there is no concurrent
        # writer, so the tail consume below sees a quiesced watermark and cannot
        # double-bill the interval the last beat may have been mid-way through.
        accrue = self._is_session_live()
        # Read the session's outcome while the pipelines are still attached.
        self._report_session_end(reason)
        self._heartbeat_stop.set()
        ht = self._heartbeat_thread
        if ht is not None and ht.is_alive():
            ht.join(timeout=1.0)
        self._heartbeat_thread = None

        # Tail report covering the time since the last heartbeat, consumed
        # atomically while session state is still set. Captured before the
        # session_id is cleared so an immediate restart cannot lose it.
        sid, delta, source = self._consume_minutes(accrue=accrue)
        tail_engine = self.current_engine() or "gemini"  # capture before pipelines clear

        self._stop_volume_mirror()

        # Keep the last seconds of paid voice before the pipelines are dropped:
        # the A/B card is offered AFTER the session, when the user is finally
        # looking at Voxis instead of at what they came to watch.
        inc = self.incoming()
        if inc is not None:
            try:
                pcm = inc.recent_pro_pcm()
                if pcm:   # a cascade session has none; keep the last paid snapshot
                    self._last_pro_pcm = pcm
            except Exception:
                pass

        for p in self._pipelines:
            try:
                p.stop()
            except Exception as e:
                self.on_status(t("st_stop_err", e=e))
        if self._pipelines:
            self.on_status(t("st_stopped"))
        self._pipelines = []
        self.mode = None
        with self._heartbeat_lock:
            self._session_id    = None
            self._session_start = None
            self._session_mode  = None
            self._last_report   = None
        self._restore_defaults()

        # Client clamp: a single tail delta cannot exceed one heartbeat interval
        # plus the bounded join wait — anything larger means a clock/state glitch,
        # so drop it rather than send the server an implausible bill. The server
        # remains the billing authority and re-derives minutes from its own
        # observed session state regardless.
        if sid and delta > 0:
            assert source is not None  # _consume_minutes: sid and source are set together
            max_tail = (self.HEARTBEAT_SECONDS + 2.0) / 60.0
            voxis_client.report_usage_async(sid, min(delta, max_tail), source, tail_engine)
            self._dispatch_usage_reported()
