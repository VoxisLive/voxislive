"""Release notes: shown once per update, never to a first-time user.

The card exists because Store updates are silent — a returning user had no way to
learn what changed. That makes two failure modes worth pinning: showing it twice
(annoying, and it trains people to dismiss it unread) and showing it to someone
who just installed the app, who has no "before" to compare against.
"""
import pytest

from app import whatsnew
from app.webui import Bridge


class _Cfg(dict):
    """cfg plus the save hook Bridge._save_cfg would touch."""


def _bridge(cfg, version="1.0.50", notes=None, monkeypatch=None, lang="en"):
    from app import i18n
    b = Bridge.__new__(Bridge)
    b.cfg = cfg
    b._save_cfg = lambda: True
    monkeypatch.setattr("app.webui.APP_VERSION", version)
    monkeypatch.setattr(whatsnew, "NOTES", notes if notes is not None else whatsnew.NOTES)
    # The UI language is process-global state another test may have set; pin it
    # so these assertions are about the gate, not about who ran first.
    monkeypatch.setattr(i18n, "_current", lang)
    return b


@pytest.fixture
def notes():
    return {"1.0.50": {"en": ["English bullet"], "tr": ["Türkçe madde"]}}


def test_returning_user_sees_the_notes_once(monkeypatch, notes):
    cfg = _Cfg(onboarding_done=True, whatsnew_seen="1.0.49")
    b = _bridge(cfg, notes=notes, monkeypatch=monkeypatch)

    first = b.whatsnew()
    assert first["version"] == "1.0.50"
    assert first["bullets"] == ["English bullet"]

    b.mark_whatsnew_seen()
    assert cfg["whatsnew_seen"] == "1.0.50"
    assert b.whatsnew() is None          # second launch: nothing


def test_fresh_install_is_marked_silently(monkeypatch, notes):
    """A brand-new user gets the onboarding tour instead; marking it here stops
    the card from ambushing them right after the tour on the next launch."""
    cfg = _Cfg(onboarding_done=False, whatsnew_seen="")
    b = _bridge(cfg, notes=notes, monkeypatch=monkeypatch)

    assert b.whatsnew() is None
    assert cfg["whatsnew_seen"] == "1.0.50"


def test_notes_render_in_the_ui_language(monkeypatch, notes):
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.49"),
                notes=notes, monkeypatch=monkeypatch, lang="tr")
    assert b.whatsnew()["bullets"] == ["Türkçe madde"]


def test_untranslated_language_falls_back_to_english(monkeypatch, notes):
    # "hu" is absent from this version's table on purpose.
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.49"),
                notes=notes, monkeypatch=monkeypatch, lang="hu")
    assert b.whatsnew()["bullets"] == ["English bullet"]


def test_version_without_notes_shows_nothing(monkeypatch, notes):
    """A release that forgets to add notes degrades to the old silence rather
    than opening an empty dialog."""
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.48"),
                version="9.9.9", notes=notes, monkeypatch=monkeypatch)
    assert b.whatsnew() is None
    assert whatsnew.entry("9.9.9", "en") == []
    assert whatsnew.has_notes("9.9.9") is False


# ---- the shipped table ---------------------------------------------------

def test_shipped_notes_cover_every_ui_language():
    """A missing language would silently read English for those users."""
    from app import i18n
    for version, per_lang in whatsnew.NOTES.items():
        missing = sorted(set(i18n.STRINGS) - set(per_lang))
        assert not missing, f"{version} missing: {missing}"
        assert all(per_lang.values()), f"{version} has an empty language"


def test_the_version_being_shipped_has_notes():
    """The gate degrades to silence on a version with no entry, which is the right
    runtime behaviour but a bad release outcome: bumping APP_VERSION and forgetting
    `python scripts/gen_whatsnew.py <ver>` ships an update nobody is told about, and
    every other test here would still pass. Fail the build instead."""
    from app import APP_VERSION
    assert whatsnew.has_notes(APP_VERSION), (
        f"app/whatsnew.py has no notes for {APP_VERSION} — "
        f"run: python scripts/gen_whatsnew.py {APP_VERSION}"
    )
