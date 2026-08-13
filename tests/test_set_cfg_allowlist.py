"""Bridge.set_cfg must only accept keys with an explicit, reviewed reason to
be settable through this generic escape hatch. Keys with their own dedicated,
validated setter (transcript_dir -> choose_transcript_dir being the motivating
case: it probes writability before persisting, a check set_cfg has no way to
replicate) must stay unreachable here even though they are real cfg keys
elsewhere -- otherwise set_cfg is a second, unvalidated way to write them.
"""
import re
import threading
from pathlib import Path

from app import webui
from app.webui import Bridge

WEB_DIR = Path(__file__).parents[1] / "app" / "web"
APP_JS = (WEB_DIR / "app.js").read_text(encoding="utf-8")


def _bare_bridge():
    b = object.__new__(Bridge)
    b.cfg = {}
    b._save_lock = threading.Lock()
    return b


def test_unlisted_key_is_rejected(monkeypatch):
    saved = []
    monkeypatch.setattr(webui, "save_config", lambda cfg: saved.append(dict(cfg)))
    b = _bare_bridge()
    assert b.set_cfg("transcript_dir", "\\\\attacker-share\\evil") is False
    assert "transcript_dir" not in b.cfg
    assert saved == []


def test_allowlisted_key_is_persisted(monkeypatch):
    saved = []
    monkeypatch.setattr(webui, "save_config", lambda cfg: saved.append(dict(cfg)))
    monkeypatch.setattr(webui.i18n, "set_language", lambda lang: None)
    b = _bare_bridge()
    assert b.set_cfg("ui_language", "tr") is True
    assert b.cfg["ui_language"] == "tr"
    assert saved and saved[-1]["ui_language"] == "tr"


def test_allowlist_covers_every_key_app_js_actually_sets():
    called = set(re.findall(r"set_cfg\(\s*'([A-Za-z_][A-Za-z0-9_]*)'", APP_JS))
    missing = called - Bridge._SET_CFG_ALLOWED_KEYS
    assert not missing, (
        f"app.js calls set_cfg('{sorted(missing)}', ...) but "
        "Bridge._SET_CFG_ALLOWED_KEYS does not list it — the call would "
        "silently be rejected at runtime."
    )


def test_dedicated_setter_keys_stay_off_the_generic_allowlist():
    # transcript_dir has its own validated setter (choose_transcript_dir probes
    # writability before persisting); set_cfg must never be a bypass for it.
    assert "transcript_dir" not in Bridge._SET_CFG_ALLOWED_KEYS
