"""IncomingPipeline must pass clone_override into make_translator only when
the routed engine is Qwen, the mode is "once" (the only value the UI still
offers — see config.VOICE_CLONE_MODES for why "always" was pulled), and Qwen
can actually VOICE the target — mirrors test_voice_gender_pipeline.py's
approach of stubbing the audio layer and inspecting make_translator's kwargs.
"""
import pytest

from app import pipeline as P


class _Stub:
    """Swallows whatever the constructor wants; records nothing."""

    def __init__(self, *a, **kw):
        self.rate = 16000
        self.tts_gain = 1.0

    def __getattr__(self, name):
        return lambda *a, **kw: None


@pytest.fixture
def built(monkeypatch):
    """Constructs a real IncomingPipeline with the audio/capture layers
    stubbed out, and returns the kwargs make_translator was called with."""
    seen = {}

    def _fake_make(cfg, target, **kw):
        seen.update(kw)
        seen["target"] = target
        return _Stub()

    monkeypatch.setattr(P, "make_translator", _fake_make)
    monkeypatch.setattr(P, "Player", _Stub)
    monkeypatch.setattr(P, "RTTEstimator", _Stub)
    monkeypatch.setattr(P, "find_device", lambda *a, **kw: None)
    monkeypatch.setattr(P, "resolve_name", lambda *a, **kw: "Speakers")
    # _acquire_capture pulls in the real WASAPI/PortAudio stack; the
    # clone_override decision is fully made before it runs, so a no-op stub
    # keeps this test off real hardware without touching what it verifies.
    monkeypatch.setattr(P.IncomingPipeline, "_acquire_capture", lambda self, *a, **kw: None)

    def _build(cfg, engine="qwen"):
        seen.clear()
        P.IncomingPipeline(
            cfg, lambda target: (engine, "key", "model", None),
            "video", lambda *a: None, lambda *a: None)
        return seen

    return _build


def _cfg(**kw):
    base = {"devices": {"microphone": "", "meeting_mic_playback": "",
                        "headphones_output": ""},
            "target_language_incoming": "cs",     # a Qwen-voiced target
            "original_audio": "duck", "duck_gain": 0.3}
    base.update(kw)
    return base


def test_clone_once_reaches_make_translator_on_qwen(built):
    kw = built(_cfg(voice_clone_incoming="once"))
    assert kw["clone_override"] == "once"


def test_stale_always_from_earlier_testing_is_ignored(built):
    # "always" was UI-selectable during 2026-08-16 testing before being pulled
    # (config.VOICE_CLONE_MODES docstring) — a config.json that still carries
    # it from that window must NOT silently re-enable a mode the UI no longer
    # offers a way to turn on.
    kw = built(_cfg(voice_clone_incoming="always"))
    assert kw["clone_override"] is None


def test_clone_off_sends_none(built):
    assert built(_cfg(voice_clone_incoming="off"))["clone_override"] is None
    assert built(_cfg())["clone_override"] is None          # key absent entirely


def test_clone_ignored_on_a_gemini_routed_target(built):
    # Gemini has no voice-clone capability at all (config.py's Absent-table
    # entry); clone_override must never reach it even if the user's setting
    # is on — e.g. a target Qwen doesn't voice, so routing picked Gemini.
    kw = built(_cfg(voice_clone_incoming="once", target_language_incoming="ja"),
              engine="gemini")
    assert kw["clone_override"] is None


def test_clone_ignored_on_a_qwen_text_only_target(built):
    # qwen_can_voice() false for a target in Qwen's ~31 text-only tier even
    # though engine routing (in this contrived test) still says "qwen" —
    # defense-in-depth: the invariant "self._engine is qwen only for a target
    # qwen can voice" should already prevent this, but the gate must hold
    # even if that invariant is ever violated.
    kw = built(_cfg(voice_clone_incoming="once", target_language_incoming="ro"))
    assert kw["clone_override"] is None
