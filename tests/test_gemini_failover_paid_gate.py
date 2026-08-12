"""Gemini failover (on_fatal) is a paid perk (2026-08-12 cost-pressure policy
— see .vault/decision-log.md): a free/taste session must never buy a Gemini
session just because Qwen died mid-session, so `on_fatal` must be wired to
`_failover_to_gemini` only when `cfg["_paid_customer"]` is truthy, and left
`None` otherwise (BaseTranslator._give_up then just surfaces the existing
connection-error status instead of substituting an engine — see
test_engine_failover.py's test_gemini_is_the_last_resort for that path).

Both IncomingPipeline and OutgoingPipeline wire this independently, so both
are pinned here — the same class of drift that would silently reintroduce
free-tier Gemini spend if only one of the two were fixed.
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


def _incoming_cfg(paid):
    cfg = {
        "devices": {"headphones_output": ""},
        "target_language_incoming": "ru",
        "speaker_labels": False,
        "tts_volume": 1.0,
        "max_ambient_delay_ms": 400,
    }
    if paid is not None:
        cfg["_paid_customer"] = paid
    return cfg


def _outgoing_cfg(paid):
    cfg = {
        "devices": {"microphone": "", "meeting_mic_playback": ""},
        "target_language_outgoing": "en",
    }
    if paid is not None:
        cfg["_paid_customer"] = paid
    return cfg


def _seen_on_fatal(monkeypatch, build):
    """Runs `build`, which must construct a pipeline whose translator
    construction is stubbed to record kwargs then raise (mirrors
    test_pipeline_teardown.py's failure-path pattern — the on_fatal wiring
    happens before capture acquisition, so this needs nothing else stubbed).
    Returns the on_fatal value make_translator was called with."""
    seen = {}

    def fake_make_translator(cfg, target, *, on_fatal=None, **kw):
        seen["on_fatal"] = on_fatal
        raise RuntimeError("stop before capture acquisition")

    monkeypatch.setattr(pipeline, "make_translator", fake_make_translator)
    with pytest.raises(RuntimeError, match="stop before capture acquisition"):
        build()
    return seen["on_fatal"]


@pytest.mark.parametrize("paid", [None, False])
def test_incoming_no_failover_when_not_paid(monkeypatch, paid):
    monkeypatch.setattr(pipeline, "find_device", lambda *a, **k: 1)
    monkeypatch.setattr(pipeline, "resolve_name", lambda *a, **k: "Headphones")
    monkeypatch.setattr(pipeline, "Player", _Resource)

    def build():
        pipeline.IncomingPipeline(
            _incoming_cfg(paid), lambda target: (ENGINE_QWEN, "key", "model", None),
            "video", lambda *a: None, lambda *a: None)

    assert _seen_on_fatal(monkeypatch, build) is None


def test_incoming_failover_wired_when_paid(monkeypatch):
    monkeypatch.setattr(pipeline, "find_device", lambda *a, **k: 1)
    monkeypatch.setattr(pipeline, "resolve_name", lambda *a, **k: "Headphones")
    monkeypatch.setattr(pipeline, "Player", _Resource)

    def build():
        pipeline.IncomingPipeline(
            _incoming_cfg(True), lambda target: (ENGINE_QWEN, "key", "model", None),
            "video", lambda *a: None, lambda *a: None)

    on_fatal = _seen_on_fatal(monkeypatch, build)
    assert on_fatal is not None
    assert on_fatal.__self__.__class__ is pipeline.IncomingPipeline
    assert on_fatal.__func__ is pipeline.IncomingPipeline._failover_to_gemini


@pytest.mark.parametrize("paid", [None, False])
def test_outgoing_no_failover_when_not_paid(monkeypatch, paid):
    monkeypatch.setattr(pipeline, "find_device", lambda *a, **k: 1)
    monkeypatch.setattr(pipeline, "Player", _Resource)
    monkeypatch.setattr(pipeline.sysaudio, "make_virtual_mic", lambda: "mic-handle")
    monkeypatch.setattr(pipeline.sysaudio, "snapshot_own_audio_streams", lambda: set())
    monkeypatch.setattr(pipeline.sysaudio, "pin_newest_own_stream_to_mic", lambda *a: 1)
    monkeypatch.setattr(pipeline.sysaudio, "teardown_virtual_mic", lambda *a: None)

    def build():
        pipeline.OutgoingPipeline(
            _outgoing_cfg(paid), lambda target: (ENGINE_QWEN, "key", "model", None),
            lambda *a: None, lambda *a: None)

    assert _seen_on_fatal(monkeypatch, build) is None


def test_outgoing_failover_wired_when_paid(monkeypatch):
    monkeypatch.setattr(pipeline, "find_device", lambda *a, **k: 1)
    monkeypatch.setattr(pipeline, "Player", _Resource)
    monkeypatch.setattr(pipeline.sysaudio, "make_virtual_mic", lambda: "mic-handle")
    monkeypatch.setattr(pipeline.sysaudio, "snapshot_own_audio_streams", lambda: set())
    monkeypatch.setattr(pipeline.sysaudio, "pin_newest_own_stream_to_mic", lambda *a: 1)
    monkeypatch.setattr(pipeline.sysaudio, "teardown_virtual_mic", lambda *a: None)

    def build():
        pipeline.OutgoingPipeline(
            _outgoing_cfg(True), lambda target: (ENGINE_QWEN, "key", "model", None),
            lambda *a: None, lambda *a: None)

    on_fatal = _seen_on_fatal(monkeypatch, build)
    assert on_fatal is not None
    assert on_fatal.__self__.__class__ is pipeline.OutgoingPipeline
    assert on_fatal.__func__ is pipeline.OutgoingPipeline._failover_to_gemini


def test_engines_no_longer_shortens_paid_retry_budget():
    """2026-08-12 policy reversal: paid sessions get the SAME transient-retry
    budget as everyone (Qwen is the priority engine for every tier now), so
    engines.make_translator must no longer special-case
    cfg['_paid_customer'] down to a 1-retry budget — a paid Qwen translator
    keeps the class default (8), same as a free/BYOK one."""
    from app import engines
    from app.base_translator import BaseTranslator

    tr = engines.make_translator(
        {"_paid_customer": True}, "tr", engine=ENGINE_QWEN, key="k",
        model="m", on_audio=lambda d: None, on_text=lambda *a: None,
        on_status=lambda *a: None, name="in")
    assert tr.MAX_TRANSIENT_FAILURES == BaseTranslator.MAX_TRANSIENT_FAILURES == 8
