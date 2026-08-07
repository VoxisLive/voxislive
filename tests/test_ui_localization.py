"""Regression checks for visible controls that previously bypassed i18n."""

from pathlib import Path

WEB_DIR = Path(__file__).parents[1] / "app" / "web"

# index.html now only carries markup; CSS/JS/i18n data live in sibling files
# (app.css / app.js / i18n.js). Concatenate them so string-search assertions
# below don't care which physical file a given snippet lives in.
HTML = "\n".join(
    (WEB_DIR / name).read_text(encoding="utf-8")
    for name in ("index.html", "app.css", "i18n.js", "app.js")
)


def test_translation_targets_have_truthful_labels_and_working_swap_button():
    assert 'data-i18n="hear"' in HTML
    assert 'data-i18n="to_other"' in HTML
    assert 'id="langswap"' in HTML
    assert 'data-i18n-title="swap_languages"' in HTML


def test_direction_labels_are_complete_and_distinct_in_every_language():
    """The two selectors are the app's most misreadable control: both are TARGET
    languages, one per direction. Pin the structure — every UI language defines
    both, non-empty and different from each other — rather than one language's
    exact wording, which is copy and does change (it did: the "Ben duyuyorum" /
    "Karşı taraf duyuyor" pair stated a fact where this is a setting, and left
    "the language I hear now" vs "the language I will hear" open)."""
    import re

    start = HTML.index("I18N_DIRECTION_LABELS")
    block = HTML[start:HTML.index("};", start)]
    entries = re.findall(
        r'(?:^|\n)\s*"?([\w-]+)"?\s*:\s*\{hear:"(.*?)",to_other:"(.*?)",'
        r'swap_languages:"(.*?)"\}', block)
    langs = {code: (hear, other, swap) for code, hear, other, swap in entries}

    # Same 23 UI locales the rest of the app ships.
    assert len(langs) == 23, f"expected 23 locales, parsed {len(langs)}"
    assert {"tr", "en", "zh-Hant"} <= set(langs)
    for code, (hear, other, swap) in langs.items():
        assert hear.strip(), f"{code}: empty 'hear' label"
        assert other.strip(), f"{code}: empty 'to_other' label"
        assert swap.strip(), f"{code}: empty swap tooltip"
        assert hear != other, (
            f"{code}: both selectors carry the same label — the control that "
            "most needs to be unambiguous would be unreadable")


def test_idle_meter_does_not_claim_that_audio_capture_is_running():
    assert 'id="vad" role="status" aria-live="polite"' in HTML
    assert 'data-i18n-aria="waiting_signal"' in HTML
    assert 'ru:"Запустите перевод для проверки сигнала"' in HTML


def test_live_meter_separates_raw_system_audio_from_speech_detection():
    assert '.meter.signal .rods i{background:var(--green)}' in HTML
    assert "T(hasInputSignal ? 'system_audio_detected' : 'waiting_system_audio')" in HTML
    assert 'system_audio_detected:"Системный звук есть · речи пока нет"' in HTML
    assert "$('#mic').disabled = (p.mode==='video')" in HTML
    assert 'mic_meeting_only:"Микрофон · только для встречи"' in HTML


def test_history_list_accessible_name_follows_interface_language():
    assert 'id="history-list" role="listbox"' in HTML
    assert 'data-i18n-aria="history_title"' in HTML


def test_outgoing_translation_monitor_is_explicit_and_localized():
    assert 'id="monitor-outgoing"' in HTML
    assert 'data-i18n="monitor_outgoing"' in HTML
    assert 'data-i18n-title="monitor_outgoing_hint"' in HTML
    assert 'monitor_outgoing:"Слушать мой перевод"' in HTML


def test_multiple_instance_preference_is_visible_localized_and_persisted():
    assert 'id="allow-multiple-instances"' in HTML
    assert 'data-i18n="allow_multiple_instances"' in HTML
    assert 'data-i18n="allow_multiple_instances_hint"' in HTML
    assert 'allow_multiple_instances:"Разрешить несколько экземпляров приложения"' in HTML
    assert "mi.checked = !!cfg.allow_multiple_instances" in HTML
    assert "set_cfg('allow_multiple_instances', e.target.checked)" in HTML
    assert 'settings_live_note:"Most changes apply immediately"' in HTML
    assert 'settings_live_note:"Большинство изменений применяется сразу"' in HTML


def test_czech_copy_has_no_accidental_literal_wrapper_quotes():
    for bad in (
        'auth_no_account:"\\"Nemáte účet?',
        'auth_sub:"\\" · Pro zobrazení',
        'behind_suffix:"\\" s zpoždění',
        'byok_hint:"\\"Pro používání',
    ):
        assert bad not in HTML
