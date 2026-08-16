"""Bridge.set_voice_clone_incoming: allow-listed value, no-op guard, restart
on genuine change — same contract as set_voice_gender."""
from app.webui import Bridge


def _bridge(cfg, calls):
    b = Bridge.__new__(Bridge)
    b.cfg = cfg
    b._save_cfg = lambda: calls.append("save") or True
    b._maybe_restart = lambda: calls.append("restart")
    return b


def test_rejects_unknown_value():
    calls = []
    b = _bridge({"voice_clone_incoming": "off"}, calls)
    assert b.set_voice_clone_incoming("bogus") is False
    assert b.cfg["voice_clone_incoming"] == "off"
    assert calls == []


def test_sets_once_and_restarts():
    calls = []
    b = _bridge({"voice_clone_incoming": "off"}, calls)
    assert b.set_voice_clone_incoming("once") is True
    assert b.cfg["voice_clone_incoming"] == "once"
    assert calls == ["save", "restart"]


def test_always_is_rejected():
    # Pulled from VOICE_CLONE_MODES 2026-08-16 (config.py docstring) — a live
    # multi-speaker test showed it doesn't switch speakers, so it's no longer
    # settable through this door.
    calls = []
    b = _bridge({"voice_clone_incoming": "off"}, calls)
    assert b.set_voice_clone_incoming("always") is False
    assert b.cfg["voice_clone_incoming"] == "off"
    assert calls == []


def test_no_op_when_unchanged_never_restarts():
    calls = []
    b = _bridge({"voice_clone_incoming": "once"}, calls)
    assert b.set_voice_clone_incoming("once") is True
    assert calls == []
