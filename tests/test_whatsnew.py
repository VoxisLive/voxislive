"""Release notes: shown once per update, never to a first-time user, and covering
every version the user skipped.

The card exists because Store updates are silent — a returning user had no way to
learn what changed. That makes two failure modes worth pinning: showing it twice
(annoying, and it trains people to dismiss it unread) and showing it to someone
who just installed the app, who has no "before" to compare against.

A third was found in the field: Store updates land in the background and skip
versions freely, and the card used to show ONLY the running version's notes, so
1.0.50's notes reached nobody who jumped 1.0.49 -> 1.0.51 in one update. The gate
now returns one entry per unread version, which is what the range tests below pin.
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
    assert first["entries"] == [{"version": "1.0.50", "bullets": ["English bullet"]}]

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
    assert b.whatsnew()["entries"][0]["bullets"] == ["Türkçe madde"]


def test_untranslated_language_falls_back_to_english(monkeypatch, notes):
    # "hu" is absent from this version's table on purpose.
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.49"),
                notes=notes, monkeypatch=monkeypatch, lang="hu")
    assert b.whatsnew()["entries"][0]["bullets"] == ["English bullet"]


# ---- skipped versions ----------------------------------------------------

@pytest.fixture
def three():
    """Three consecutive releases, so a skip has something to lose."""
    return {
        "1.0.49": {"en": ["forty-nine"]},
        "1.0.50": {"en": ["fifty"]},
        "1.0.51": {"en": ["fifty-one"]},
    }


def test_a_skipped_version_is_not_lost(monkeypatch, three):
    """1.0.49 -> 1.0.51 in one Store update: 1.0.50 must still be shown. This is
    the exact case that reached nobody before — newest first."""
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.49"),
                version="1.0.51", notes=three, monkeypatch=monkeypatch)
    got = b.whatsnew()
    assert [e["version"] for e in got["entries"]] == ["1.0.51", "1.0.50"]
    assert got["version"] == "1.0.51"          # header still names the running build


def test_only_unread_versions_are_shown(monkeypatch, three):
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.50"),
                version="1.0.51", notes=three, monkeypatch=monkeypatch)
    assert [e["version"] for e in b.whatsnew()["entries"]] == ["1.0.51"]


def test_updating_from_before_the_feature_shows_the_whole_table(monkeypatch, three):
    """Blank whatsnew_seen + finished onboarding = updated from a build that
    predates the card, so nothing in the table has been read."""
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen=""),
                version="1.0.51", notes=three, monkeypatch=monkeypatch)
    assert [e["version"] for e in b.whatsnew()["entries"]] == ["1.0.51", "1.0.50", "1.0.49"]


def test_a_newer_table_entry_is_never_advertised(monkeypatch, three):
    """Running an older build than the table describes (a downgrade, or a stale
    bundle) must not promise features this build does not have."""
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.49"),
                version="1.0.50", notes=three, monkeypatch=monkeypatch)
    assert [e["version"] for e in b.whatsnew()["entries"]] == ["1.0.50"]


def test_patch_numbers_compare_numerically(monkeypatch):
    """"1.0.9" sorts after "1.0.10" as text, and the patch number is past 10."""
    notes = {"1.0.9": {"en": ["nine"]}, "1.0.10": {"en": ["ten"]}}
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.9"),
                version="1.0.10", notes=notes, monkeypatch=monkeypatch)
    assert [e["version"] for e in b.whatsnew()["entries"]] == ["1.0.10"]


def test_nothing_unread_leaves_the_seen_marker_alone(monkeypatch, three):
    """A release with no notes shows nothing AND must not burn the marker, so the
    next release that does have notes still opens the card."""
    cfg = _Cfg(onboarding_done=True, whatsnew_seen="1.0.51")
    b = _bridge(cfg, version="1.0.52", notes=three, monkeypatch=monkeypatch)
    assert b.whatsnew() is None
    assert cfg["whatsnew_seen"] == "1.0.51"


def test_a_release_that_forgot_its_notes_still_delivers_earlier_ones(monkeypatch, notes):
    """The running version has no entry (a release forgot to generate one). That
    used to mean silence; now the user still gets the unread entries that DO
    exist, because those changes are in this build too. The build-time gate
    (test_the_version_being_shipped_has_notes) is what catches the forgotten
    entry — the runtime should not punish the user for it."""
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.48"),
                version="9.9.9", notes=notes, monkeypatch=monkeypatch)
    assert [e["version"] for e in b.whatsnew()["entries"]] == ["1.0.50"]
    assert whatsnew.entry("9.9.9", "en") == []
    assert whatsnew.has_notes("9.9.9") is False


def test_empty_dialog_is_still_impossible(monkeypatch):
    """The original guarantee holds where it matters: when nothing unread has any
    bullets, the card does not open at all."""
    b = _bridge(_Cfg(onboarding_done=True, whatsnew_seen="1.0.48"),
                version="9.9.9", notes={"1.0.47": {"en": ["old"]}},
                monkeypatch=monkeypatch)
    assert b.whatsnew() is None


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
