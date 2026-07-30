"""Language-direction controls must update both targets as one operation."""

from app.webui import Bridge


def test_language_swap_is_atomic():
    bridge = Bridge.__new__(Bridge)
    bridge.cfg = {
        "target_language_incoming": "ru",
        "target_language_outgoing": "en",
    }
    calls = []
    bridge._prefetch_session_key = lambda: calls.append("prefetch")
    bridge._maybe_restart = lambda: calls.append("restart")
    bridge._save_cfg = lambda: calls.append("save") or True

    result = bridge.swap_languages()

    assert result == {"ok": True, "incoming": "en", "outgoing": "ru"}
    assert bridge.cfg == {
        "target_language_incoming": "en",
        "target_language_outgoing": "ru",
    }
    assert calls == ["save", "prefetch", "restart"]


def test_language_swap_rolls_back_when_config_cannot_be_saved():
    bridge = Bridge.__new__(Bridge)
    bridge.cfg = {
        "target_language_incoming": "ru",
        "target_language_outgoing": "en",
    }
    bridge._save_cfg = lambda: False
    bridge._prefetch_session_key = lambda: (_ for _ in ()).throw(
        AssertionError("must not prefetch after a failed save"))
    bridge._maybe_restart = lambda: (_ for _ in ()).throw(
        AssertionError("must not restart after a failed save"))

    result = bridge.swap_languages()

    assert result == {"ok": False, "incoming": "ru", "outgoing": "en"}
    assert bridge.cfg == {
        "target_language_incoming": "ru",
        "target_language_outgoing": "en",
    }


# --- meeting terms (hotwords) -----------------------------------------------

def _hotword_bridge(cfg):
    import threading
    from app.webui import Bridge
    b = object.__new__(Bridge)
    b.cfg = cfg
    b._cfg_lock = threading.RLock()
    b._save_cfg = lambda: True
    b._maybe_restart = lambda: None
    return b


def test_set_hotwords_keeps_the_other_beta_knobs():
    """cfg["beta"] also holds clone / source_lang / vad_ms, which are
    config-file-only. Writing the term list must not reset them."""
    cfg = {"beta": {"enabled": False, "clone": "once",
                    "source_lang": "en", "vad_ms": 400, "hotwords": ""}}
    b = _hotword_bridge(cfg)
    b.set_hotwords("Antler\nMENAP=MENAP")
    assert cfg["beta"]["hotwords"] == "Antler\nMENAP=MENAP"
    assert cfg["beta"]["clone"] == "once"
    assert cfg["beta"]["source_lang"] == "en"
    assert cfg["beta"]["vad_ms"] == 400


def test_set_hotwords_creates_the_beta_block_when_absent():
    cfg = {}
    b = _hotword_bridge(cfg)
    b.set_hotwords("Voxis")
    assert cfg["beta"]["hotwords"] == "Voxis"


def test_set_hotwords_is_bounded():
    from app.webui import HOTWORDS_MAX_CHARS
    cfg = {"beta": {}}
    b = _hotword_bridge(cfg)
    b.set_hotwords("x" * (HOTWORDS_MAX_CHARS + 500))
    assert len(cfg["beta"]["hotwords"]) == HOTWORDS_MAX_CHARS


def test_hotword_stats_match_the_engine_parser():
    """The number shown in Settings must be the number actually sent, so it is
    derived from the same parser engines.py feeds to the session. Since the
    prepacked list rides along, the readout also has to separate what the user
    typed from what shipped with the app."""
    from app.config import DEFAULT_TERMS
    b = _hotword_bridge({"beta": {}, "builtin_terms": False})
    assert b.hotword_stats("Antler\n\n# a comment\nMENAP=MENAP")["user"] == 2
    assert b.hotword_stats("")["user"] == 0
    assert b.hotword_stats("Antler")["total"] == 1      # list off: user only

    b = _hotword_bridge({"beta": {}, "builtin_terms": True})
    stats = b.hotword_stats("Antler")
    assert stats["user"] == 1
    assert stats["builtin"] == len(DEFAULT_TERMS)
    assert stats["total"] == 1 + len(DEFAULT_TERMS)
