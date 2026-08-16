"""Qwen voice-cloning must ride ONLY a genuine beta session.

Field bug (Ivo Kapec, 2026-07-17): a stale `beta.clone="always"` left in
config.json by an old Beta-tab soak silently turned per-speaker voice cloning on
for the now-standard Qwen route, which mis-genders male source speakers as a
female voice. `make_translator` used to read cfg["beta"]["clone"]
unconditionally; it now gates it on `beta_active`, which webui sets True only on
a real server-authorized beta resolver. These pin that gate so a refactor can't
quietly re-open the hole.
"""
import json

from app.config import ENGINE_QWEN
from app.engines import make_translator


def _make(cfg, *, beta_active):
    return make_translator(
        cfg, "cs", engine=ENGINE_QWEN, key="dummy-key", model="test-model",
        on_audio=lambda *_: None, on_text=lambda *_: None,
        on_status=lambda *_: None, name="t", beta_active=beta_active)


def test_stale_clone_ignored_on_standard_route():
    # config carries clone=always (the soak leftover) but this is NOT a beta
    # session → clone must be forced off.
    cfg = {"beta": {"enabled": True, "clone": "always"}}
    tr = _make(cfg, beta_active=False)
    assert tr.clone == "off"
    # And the wire config must not carry any voice/clone fields.
    session = json.loads(tr._session_update())["session"]
    assert "voice" not in session
    assert "enable_voice_clone" not in session
    assert "voice_clone_options" not in session


def test_clone_honored_on_genuine_beta_session():
    cfg = {"beta": {"enabled": True, "clone": "always"}}
    tr = _make(cfg, beta_active=True)
    assert tr.clone == "always"
    session = json.loads(tr._session_update())["session"]
    assert session["voice"] == "default"          # cloning REQUIRES voice=default
    assert session["enable_voice_clone"] is True
    assert session["voice_clone_options"] == {"frequency": "always"}


def test_default_is_off_even_in_beta():
    # No clone key at all → off regardless of beta_active.
    tr = _make({"beta": {"enabled": True}}, beta_active=True)
    assert tr.clone == "off"
    assert "enable_voice_clone" not in json.loads(tr._session_update())["session"]


# --- clone_override: the first-class voice_clone_incoming door -------------
#
# Independent of beta_active/cfg["beta"]["clone"] entirely — the standard
# (non-beta) route's own opt-in for cloning the incoming speaker's voice.


def _make_with_override(cfg, clone_override, *, beta_active=False):
    return make_translator(
        cfg, "cs", engine=ENGINE_QWEN, key="dummy-key", model="test-model",
        on_audio=lambda *_: None, on_text=lambda *_: None,
        on_status=lambda *_: None, name="t", beta_active=beta_active,
        clone_override=clone_override)


def test_clone_override_once_honored_on_standard_route():
    tr = _make_with_override({}, "once")
    assert tr.clone == "once"
    session = json.loads(tr._session_update())["session"]
    assert session["enable_voice_clone"] is True
    assert session["voice_clone_options"] == {"frequency": "once"}


def test_clone_override_always_honored_on_standard_route():
    tr = _make_with_override({}, "always")
    assert tr.clone == "always"
    session = json.loads(tr._session_update())["session"]
    assert session["voice_clone_options"] == {"frequency": "always"}


def test_clone_override_wins_over_a_stale_beta_clone_field():
    # A stale beta.clone="always" from an old soak must not leak through even
    # when clone_override explicitly says "off" — override always wins.
    cfg = {"beta": {"enabled": True, "clone": "always"}}
    tr = _make_with_override(cfg, "off", beta_active=True)
    assert tr.clone == "off"
    assert "enable_voice_clone" not in json.loads(tr._session_update())["session"]


def test_clone_override_none_falls_back_to_the_beta_active_gate():
    # clone_override=None (the default) must not change the pre-existing
    # beta_active-gated behavior at all.
    cfg = {"beta": {"enabled": True, "clone": "always"}}
    assert _make_with_override(cfg, None, beta_active=False).clone == "off"
    assert _make_with_override(cfg, None, beta_active=True).clone == "always"
