"""Each meeting leg carries ITS OWN voice into the session handshake.

Both legs are built from the same cfg dict, so the resolution has to happen per
leg at the call site. If a refactor ever collapses them onto one key, the other
party would hear the user in the voice meant for the user's own playback — the
exact confusion this feature was asked for to remove.
"""
import pytest

from app import pipeline as P


class _Stub:
    """Swallows whatever the constructor wants; records nothing."""

    def __init__(self, *a, **kw):
        self.rate = 16000

    def __getattr__(self, name):
        return lambda *a, **kw: None


@pytest.fixture
def built(monkeypatch):
    """Constructs a real OutgoingPipeline with the audio layer stubbed out, and
    returns the kwargs make_translator was called with."""
    seen = {}

    def _fake_make(cfg, target, **kw):
        seen.update(kw)
        seen["target"] = target
        return _Stub()

    monkeypatch.setattr(P, "make_translator", _fake_make)
    monkeypatch.setattr(P, "Player", _Stub)
    monkeypatch.setattr(P, "Capture", _Stub)
    monkeypatch.setattr(P, "find_device", lambda *a, **kw: None)
    monkeypatch.setattr(P.sysaudio, "make_virtual_mic", lambda: None)
    monkeypatch.setattr(P.sysaudio, "snapshot_own_audio_streams", list)
    monkeypatch.setattr(P, "_GatedSource", _Stub)
    # The outgoing leg now builds a real catch-up stager for Qwen/Gemini (see
    # test_outgoing_playback_stager.py) — its own background thread has no
    # place in a gender-routing test, so keep it a stub here too.
    monkeypatch.setattr(P, "AdaptivePlaybackStager", _Stub)

    def _build(cfg):
        seen.clear()
        P.OutgoingPipeline(cfg, lambda target: ("qwen", "key", "model", None),
                           lambda *a: None, lambda *a: None)
        return seen

    return _build


def _cfg(**kw):
    base = {"devices": {"microphone": "", "meeting_mic_playback": "",
                        "headphones_output": ""},
            "target_language_outgoing": "en",
            "target_language_incoming": "tr"}
    base.update(kw)
    return base


def test_outgoing_leg_uses_its_own_gender(built):
    kw = built(_cfg(voice_gender_outgoing="male", voice_gender_incoming="female"))
    assert kw["voice"] == "Ethan"       # the OUTGOING setting, not the incoming one
    assert kw["target"] == "en"


def test_outgoing_leg_female(built):
    assert built(_cfg(voice_gender_outgoing="female"))["voice"] == "Tina"


def test_auto_sends_no_voice(built):
    """Existing users upgrade into exactly the behaviour they had."""
    assert built(_cfg(voice_gender_outgoing="auto"))["voice"] is None
    assert built(_cfg())["voice"] is None          # key absent entirely


def test_gemini_routed_leg_gets_no_voice(built, monkeypatch):
    """Gemini ignores the field (measured), so nothing is sent even when the
    user asked for a gender — the UI tells them why instead of lying."""
    seen = {}

    def _fake_make(cfg, target, **kw):
        seen.update(kw)
        return _Stub()

    monkeypatch.setattr(P, "make_translator", _fake_make)
    P.OutgoingPipeline(_cfg(voice_gender_outgoing="male"),
                       lambda target: ("gemini", "key", "model", None),
                       lambda *a: None, lambda *a: None)
    assert seen["voice"] is None
