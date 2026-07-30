"""Voice gender: the requested gender must reach the engine that honors it.

Measured 2026-07-30 (vault: qwen-preset-voice-measurement): Qwen honors
session.voice — Tina reads female (F0 ~261 Hz), Ethan male (~170 Hz), and the two
arms are different voices by CAM++ cosine (0.34). Gemini's translate-preview
ignores the field entirely — five valid names AND a garbage name returned one
voice — so a gender request must NOT be turned into a Gemini voice name, and the
Qwen field must stay absent unless a verified name was chosen.

Cloning is the one case where the name must be dropped: DashScope rejects a named
voice alongside enable_voice_clone outright, which would strand the session.
"""
import json

import pytest

from app import engines
from app.config import VOICE_BY_GENDER, resolve_voice
from app.qwen_translator import QwenTranslator


def _qwen(**kw):
    kw.setdefault("target_lang", "en")
    return QwenTranslator(api_key="k", on_audio=lambda *a: None,
                          on_text=lambda *a: None, on_status=lambda *a: None, **kw)


def _session(tr):
    return json.loads(tr._session_update())["session"]


# ---- the mapping ---------------------------------------------------------

def test_qwen_maps_gender_to_the_verified_names():
    assert resolve_voice("qwen", "female") == "Tina"
    assert resolve_voice("qwen", "male") == "Ethan"


def test_auto_and_unknown_requests_resolve_to_no_voice():
    for gender in ("auto", "", None, "other"):
        assert resolve_voice("qwen", gender) is None


def test_gemini_has_no_gender_mapping():
    """The translate model ignores the voice field; promising a gender there
    would be a lie the UI then has to explain away."""
    assert "gemini" not in VOICE_BY_GENDER
    assert resolve_voice("gemini", "male") is None
    assert resolve_voice("cascade", "female") is None


# ---- what actually rides the handshake -----------------------------------

def test_named_voice_is_sent_when_not_cloning():
    assert _session(_qwen(voice="Ethan"))["voice"] == "Ethan"


def test_no_voice_key_at_all_without_a_request():
    """auto must serialize exactly as it did before this feature existed."""
    assert "voice" not in _session(_qwen())
    assert "voice" not in _session(_qwen(voice=None))


def test_cloning_wins_and_drops_the_named_voice():
    """DashScope: "Multilingual voice does not support voice clone" — sending
    both is a hard reject, and the clone already carries the speaker's gender."""
    s = _session(_qwen(voice="Ethan", clone="always"))
    assert s["voice"] == "default"
    assert s["enable_voice_clone"] is True


# ---- the factory ---------------------------------------------------------

def test_factory_forwards_voice_to_qwen(monkeypatch):
    seen = {}

    class _Fake:
        def __init__(self, *a, **kw):
            seen.update(kw)

    monkeypatch.setattr("app.qwen_translator.QwenTranslator", _Fake)
    engines.make_translator({"beta": {}}, "en", engine="qwen", key="k",
                            on_audio=None, on_text=None, on_status=None,
                            name="t", voice="Tina")
    assert seen["voice"] == "Tina"


def test_factory_does_not_hand_a_voice_to_gemini(monkeypatch):
    """LiveTranslator's voice comes from cfg["gemini_voice"]; a gender must not
    leak into it, or the config would silently disagree with the picker."""
    seen = {}

    class _Fake:
        def __init__(self, *a, **kw):
            seen.update(kw)

    monkeypatch.setattr("app.translator.LiveTranslator", _Fake)
    engines.make_translator({"gemini_voice": "Aoede"}, "en", engine="gemini",
                            key="k", on_audio=None, on_text=None, on_status=None,
                            name="t", voice="Ethan")
    assert seen["voice"] == "Aoede"


# ---- the two legs are independent ---------------------------------------

@pytest.mark.parametrize("incoming,outgoing,want_in,want_out", [
    ("male", "female", "Ethan", "Tina"),
    ("female", "male", "Tina", "Ethan"),
    ("auto", "male", None, "Ethan"),
    ("male", "auto", "Ethan", None),
])
def test_each_leg_resolves_its_own_gender(incoming, outgoing, want_in, want_out):
    """A meeting speaks with two voices — the other party's and the user's — and
    both legs read the same cfg, so the resolution has to be per leg."""
    cfg = {"voice_gender_incoming": incoming, "voice_gender_outgoing": outgoing}
    assert resolve_voice("qwen", cfg["voice_gender_incoming"]) == want_in
    assert resolve_voice("qwen", cfg["voice_gender_outgoing"]) == want_out
