"""Cascade rescue (on_fatal -> _swap_to_cascade) is the free/taste-tier
counterpart of the paid Gemini failover: a session still inside its one-time
15-minute Pro taste gets a shot at a server-granted cascade key instead of
just ending when Qwen dies mid-session (2026-08-13 — see
.vault/decision-log.md).

Wiring rules pinned here:
- paid always wins over taste_rescue (a paid+taste combination shouldn't
  occur in practice, but if it ever does, the paid perk — full Gemini audio,
  not a local voice — must not be shadowed by the free-tier path).
- taste_rescue wires _failover_to_cascade only when NOT paid.
- Neither flag: on_fatal stays None, same as before this feature existed.
- OutgoingPipeline (Meeting-only) never wires the cascade rescue at all —
  cascade must never reach Meeting mode regardless of this flag, and
  Outgoing structurally only exists inside Meeting sessions.
"""
import pytest

import app.pipeline as pipeline
from app.config import ENGINE_QWEN


class _Resource:
    def __init__(self, *args, **kwargs):
        self.rate = 48000
        self.tts_gain = 1.0

    def stop(self):
        pass


def _incoming_cfg(paid=None, taste_rescue=None):
    cfg = {
        "devices": {"headphones_output": ""},
        "target_language_incoming": "ru",
        "speaker_labels": False,
        "tts_volume": 1.0,
        "max_ambient_delay_ms": 400,
    }
    if paid is not None:
        cfg["_paid_customer"] = paid
    if taste_rescue is not None:
        cfg["_taste_rescue_eligible"] = taste_rescue
    return cfg


def _outgoing_cfg(paid=None, taste_rescue=None):
    cfg = {
        "devices": {"microphone": "", "meeting_mic_playback": ""},
        "target_language_outgoing": "en",
    }
    if paid is not None:
        cfg["_paid_customer"] = paid
    if taste_rescue is not None:
        cfg["_taste_rescue_eligible"] = taste_rescue
    return cfg


def _seen_on_fatal(monkeypatch, build):
    seen = {}

    def fake_make_translator(cfg, target, *, on_fatal=None, **kw):
        seen["on_fatal"] = on_fatal
        raise RuntimeError("stop before capture acquisition")

    monkeypatch.setattr(pipeline, "make_translator", fake_make_translator)
    with pytest.raises(RuntimeError, match="stop before capture acquisition"):
        build()
    return seen["on_fatal"]


def _build_incoming(cfg, monkeypatch):
    monkeypatch.setattr(pipeline, "find_device", lambda *a, **k: 1)
    monkeypatch.setattr(pipeline, "resolve_name", lambda *a, **k: "Headphones")
    monkeypatch.setattr(pipeline, "Player", _Resource)

    def build():
        pipeline.IncomingPipeline(
            cfg, lambda target, **kw: (ENGINE_QWEN, "key", "model", None),
            "video", lambda *a: None, lambda *a: None)
    return _seen_on_fatal(monkeypatch, build)


def test_incoming_no_rescue_when_neither_flag(monkeypatch):
    assert _build_incoming(_incoming_cfg(), monkeypatch) is None


def test_incoming_rescue_wired_when_taste_active(monkeypatch):
    on_fatal = _build_incoming(_incoming_cfg(paid=False, taste_rescue=True), monkeypatch)
    assert on_fatal is not None
    assert on_fatal.__self__.__class__ is pipeline.IncomingPipeline
    assert on_fatal.__func__ is pipeline.IncomingPipeline._failover_to_cascade


def test_incoming_paid_wins_over_taste_rescue(monkeypatch):
    """Both flags set (shouldn't happen in practice — see module docstring)
    must still resolve to the paid Gemini failover, not the free path."""
    on_fatal = _build_incoming(_incoming_cfg(paid=True, taste_rescue=True), monkeypatch)
    assert on_fatal.__func__ is pipeline.IncomingPipeline._failover_to_gemini


def test_incoming_no_rescue_when_taste_flag_false(monkeypatch):
    assert _build_incoming(_incoming_cfg(paid=False, taste_rescue=False), monkeypatch) is None


def test_outgoing_never_wires_cascade_rescue(monkeypatch):
    """Meeting-only pipeline: even if a caller mistakenly set the taste-
    rescue flag on it, on_fatal must not resolve to the cascade path — the
    outgoing construction site never wires it at all (unlike incoming)."""
    monkeypatch.setattr(pipeline, "find_device", lambda *a, **k: 1)
    monkeypatch.setattr(pipeline, "Player", _Resource)
    monkeypatch.setattr(pipeline.sysaudio, "make_virtual_mic", lambda: "mic-handle")
    monkeypatch.setattr(pipeline.sysaudio, "snapshot_own_audio_streams", lambda: set())
    monkeypatch.setattr(pipeline.sysaudio, "pin_newest_own_stream_to_mic", lambda *a: 1)
    monkeypatch.setattr(pipeline.sysaudio, "teardown_virtual_mic", lambda *a: None)

    def build():
        pipeline.OutgoingPipeline(
            _outgoing_cfg(paid=False, taste_rescue=True),
            lambda target, **kw: (ENGINE_QWEN, "key", "model", None),
            lambda *a: None, lambda *a: None)

    assert _seen_on_fatal(monkeypatch, build) is None
