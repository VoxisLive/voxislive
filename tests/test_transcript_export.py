"""transcript_store: bilingual vs translated-only export rendering."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import app.transcript_store as ts


def _rec():
    return {
        "version": 1,
        "started": 0.0,
        "turns": [
            {"t": 0.0, "dir": "in", "src": "Merhaba dünya", "text": "Hello world"},
            {"t": 3.0, "dir": "in", "src": "Nasilsin", "text": "How are you"},
            # A turn with no captured source: bilingual output falls back to the
            # translation line alone (no stray blank source line).
            {"t": 6.0, "dir": "in", "src": "", "text": "Fine thanks"},
        ],
    }


def test_txt_mono_is_translation_only():
    out = ts.render_txt(_rec())
    assert out == "Hello world\nHow are you\nFine thanks\n"
    assert "Merhaba" not in out


def test_cues_are_wrapped_and_lose_nothing():
    """A simultaneous engine that never pauses produces very long turns; an
    unwrapped cue runs off the frame (a field session hit 548 characters on one
    line). Wrapping must fold, never truncate."""
    long_tr = " ".join(["kelime"] * 90)
    rec = {"version": 1, "started": 0.0,
           "turns": [{"t": 0.0, "dir": "out", "src": "", "text": long_tr}]}
    out = ts.render_srt(rec)
    body = out.split("\n", 2)[2].strip()
    assert all(len(ln) <= ts.CUE_WIDTH for ln in body.split("\n"))
    assert body.split() == long_tr.split()          # every word survived


def test_wrap_keeps_an_overlong_word_intact():
    word = "x" * 60
    assert ts._wrap(f"bir {word} iki") == f"bir\n{word}\niki"


def test_bilingual_cue_wraps_each_language_separately():
    rec = {"version": 1, "started": 0.0, "turns": [{
        "t": 0.0, "dir": "out",
        "src": " ".join(["source"] * 20), "text": " ".join(["çeviri"] * 20)}]}
    body = ts.render_srt(rec).split("\n", 2)[2].strip()
    assert all(len(ln) <= ts.CUE_WIDTH for ln in body.split("\n"))
    # No line may mix the two languages — the fold happens per language line.
    assert not any("source" in ln and "çeviri" in ln for ln in body.split("\n"))


def test_record_omits_the_events_key_when_nothing_happened():
    """Schema-additive: an uneventful session must serialize exactly as before."""
    turns = [{"t": 0.0, "dir": "out", "src": "hi", "text": "selam"}]
    assert "events" not in ts.build_record(0.0, turns)
    assert "events" not in ts.build_record(0.0, turns, events=[])
    # Blank messages are not events either.
    assert "events" not in ts.build_record(0.0, turns, events=[{"t": 1.0, "msg": "  "}])


def test_record_keeps_engine_lifecycle_events():
    """A dropped/reconnected session must be answerable from the saved file —
    the status line used to exist only on screen (session audit 2026-07-28)."""
    turns = [{"t": 0.0, "dir": "out", "src": "hi", "text": "selam"}]
    rec = ts.build_record(0.0, turns, events=[
        {"t": 0.5, "msg": "Qwen: bağlandı (hedef: tr)"},
        {"t": 812.0, "msg": "Qwen: oturum yenileniyor..."},
    ])
    assert [e["msg"] for e in rec["events"]] == [
        "Qwen: bağlandı (hedef: tr)", "Qwen: oturum yenileniyor..."]
    assert rec["events"][1]["t"] == 812.0


def test_txt_bilingual_pairs_source_over_translation():
    out = ts.render_txt(_rec(), bilingual=True)
    assert "Merhaba dünya\nHello world" in out
    assert "Nasilsin\nHow are you" in out
    # Blank line between turns; source-less turn keeps only the translation.
    assert out.endswith("Fine thanks\n")
    assert "\n\nFine thanks" in out


def test_srt_bilingual_default_and_mono_opt_out():
    bi = ts.render_srt(_rec())
    assert "Merhaba dünya" in bi and "Hello world" in bi
    mono = ts.render_srt(_rec(), bilingual=False)
    assert "Merhaba dünya" not in mono and "Hello world" in mono


def test_export_passes_bilingual_flag():
    content, ext = ts.export(_rec(), "txt", bilingual=True)
    assert ext == "txt" and "Merhaba dünya" in content
    content, ext = ts.export(_rec(), "txt", bilingual=False)
    assert "Merhaba dünya" not in content


def test_export_unknown_format_raises():
    import pytest
    with pytest.raises(ValueError):
        ts.export(_rec(), "pdf")


def test_source_only_turn_survives_record_and_bilingual_exports():
    rec = ts.build_record(1.0, [
        {"t": 0, "dir": "out", "src": "Source survived", "text": ""},
    ])
    assert rec["turns"] == [
        {"t": 0.0, "dir": "out", "src": "Source survived", "text": ""},
    ]
    assert ts.render_txt(rec, bilingual=True) == "Source survived\n"
    assert "Source survived" in ts.render_srt(rec, bilingual=True)
    assert ts.render_txt(rec, bilingual=False) == ""


def test_concurrent_saves_always_leave_valid_json(tmp_path):
    records = [ts.build_record(1.0, [
        {"t": 0, "src": f"source-{i}", "text": f"translation-{i}"},
    ]) for i in range(24)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        paths = list(pool.map(
            lambda rec: ts.save_record(str(tmp_path), rec, subdir="voxis_same"),
            records))
    assert len(set(paths)) == 1
    saved = ts.load_record(paths[0])
    assert saved in records
    assert not list((tmp_path / "voxis_same").glob("*.tmp"))


def test_failed_save_preserves_the_previous_good_record(tmp_path, monkeypatch):
    good = ts.build_record(1.0, [{"t": 0, "src": "one", "text": "good"}])
    path = ts.save_record(str(tmp_path), good, subdir="voxis_atomic")

    def broken_dump(record, f, **kwargs):
        f.write('{"partial":')
        raise OSError("disk interrupted")

    monkeypatch.setattr(ts.json, "dump", broken_dump)
    import pytest
    with pytest.raises(OSError, match="disk interrupted"):
        ts.save_record(
            str(tmp_path), {"version": 1, "turns": []}, subdir="voxis_atomic")
    assert ts.load_record(path) == good
    assert not list((tmp_path / "voxis_atomic").glob("*.tmp"))


def test_source_track_is_omitted_when_empty():
    turns = [{"t": 0.0, "dir": "out", "src": "hi", "text": "selam"}]
    assert "source_track" not in ts.build_record(0.0, turns)
    assert "source_track" not in ts.build_record(0.0, turns, source_track=[])


def test_source_track_records_arrival_times_and_drops_internals():
    """The per-turn `src` is a PAIRING; this track is what actually arrived and
    when, so a wrong pairing can be measured and re-derived afterwards."""
    turns = [{"t": 0.0, "dir": "out", "src": "", "text": "selam"}]
    rec = ts.build_record(0.0, turns, source_track=[
        {"t": 1.5, "text": "Hello there.", "_at": 999.0},
        {"t": 4.0, "text": "  ", "_at": 999.0},          # blank: not an arrival
        {"t": 6.0, "text": "How are you?", "leg": "outgoing", "_at": 999.0},
    ])
    assert rec["source_track"] == [
        {"t": 1.5, "text": "Hello there."},
        {"t": 6.0, "text": "How are you?", "leg": "outgoing"},
    ]


def test_audio_track_is_omitted_when_empty():
    turns = [{"t": 0.0, "dir": "out", "src": "", "text": "selam"}]
    assert "audio_track" not in ts.build_record(0.0, turns)
    assert "audio_track" not in ts.build_record(0.0, turns, audio_track=[])


def test_audio_track_records_produced_speech_seconds():
    """Its slope against the turn timeline is what exposes captioned-but-never-
    spoken text — a measured session spoke 968 words against 1067 captioned."""
    turns = [{"t": 0.0, "dir": "out", "src": "", "text": "selam"}]
    rec = ts.build_record(0.0, turns, audio_track=[
        {"t": 1.0, "sec": 0.5}, {"t": 9.0, "sec": 6.25},
    ])
    assert rec["audio_track"] == [{"t": 1.0, "sec": 0.5}, {"t": 9.0, "sec": 6.25}]


# --- starred: schema-additive field + prune exemption ----------------------


def test_starred_is_schema_additive_via_overwrite_record(tmp_path):
    rec = ts.build_record(1.0, [{"t": 0, "src": "one", "text": "iki"}])
    assert "starred" not in rec
    path = ts.save_record(str(tmp_path), rec, subdir="voxis_star")

    loaded = ts.load_record(path)
    loaded["starred"] = True
    ts.overwrite_record(path, loaded)
    assert ts.load_record(path)["starred"] is True

    # Unstarring must drop the key entirely, not just set it False — an
    # unstarred record has to serialize exactly as it did before starring ever
    # existed.
    loaded = ts.load_record(path)
    loaded.pop("starred", None)
    ts.overwrite_record(path, loaded)
    assert "starred" not in ts.load_record(path)
    assert not list((tmp_path / "voxis_star").glob("*.tmp"))


def test_overwrite_record_works_on_legacy_flat_layout(tmp_path):
    # Legacy pre-1.0.28 records live directly in the transcripts root, not in
    # their own voxis_<stamp>/ folder — overwrite_record must not assume nesting.
    path = tmp_path / "voxis_flat.json"
    rec = ts.build_record(1.0, [{"t": 0, "src": "one", "text": "iki"}])
    path.write_text(json.dumps(rec), encoding="utf-8")

    rec["starred"] = True
    ts.overwrite_record(str(path), rec)
    assert ts.load_record(str(path))["starred"] is True
    assert not list(tmp_path.glob("*.tmp"))


def test_list_records_summary_carries_starred_flag(tmp_path):
    rec = ts.build_record(1.0, [{"t": 0, "src": "one", "text": "iki"}])
    path = ts.save_record(str(tmp_path), rec, subdir="voxis_star2")
    ts.invalidate_summary_cache()
    summaries = {r["file"]: r for r in ts.list_records(str(tmp_path))}
    assert summaries[os.path.basename(path)]["starred"] is False

    loaded = ts.load_record(path)
    loaded["starred"] = True
    ts.overwrite_record(path, loaded)
    ts.invalidate_summary_cache(path)
    summaries = {r["file"]: r for r in ts.list_records(str(tmp_path))}
    assert summaries[os.path.basename(path)]["starred"] is True


def test_prune_transcripts_never_removes_a_starred_session(tmp_path, monkeypatch):
    rec = ts.build_record(1.0, [{"t": 0, "src": "one", "text": "iki"}])
    old_path = ts.save_record(str(tmp_path), rec, subdir="voxis_old_starred")
    loaded = ts.load_record(old_path)
    loaded["starred"] = True
    ts.overwrite_record(old_path, loaded)

    # Age it past the retention window on disk (mtime is what prune reads).
    old_dir = tmp_path / "voxis_old_starred"
    ancient = time.time() - 200 * 86400
    os.utime(old_path, (ancient, ancient))
    os.utime(old_dir, (ancient, ancient))

    pruned = ts.prune_transcripts(str(tmp_path), max_age_days=90, max_files=500)
    assert pruned == 0
    assert old_dir.exists()


def test_render_txt_prepends_summary_when_present():
    rec = _rec()
    rec["summary"] = "Two people discussed their day."
    out = ts.render_txt(rec)
    assert out.startswith("Two people discussed their day.\n\n---\n\n")
    assert "Hello world" in out


def test_render_txt_omits_summary_header_when_absent():
    out = ts.render_txt(_rec())
    assert "---" not in out


def test_render_txt_bilingual_also_carries_the_summary():
    rec = _rec()
    rec["summary"] = "Recap."
    out = ts.render_txt(rec, bilingual=True)
    assert out.startswith("Recap.\n\n---\n\n")


def test_render_srt_never_carries_a_summary_header():
    rec = {"version": 1, "started": 0.0, "summary": "Recap.",
           "turns": [{"t": 0.0, "dir": "out", "src": "", "text": "selam"}]}
    assert "Recap." not in ts.render_srt(rec)
    assert "Recap." not in ts.render_vtt(rec)


def test_prune_transcripts_starred_session_does_not_count_against_max_files(tmp_path):
    starred_rec = ts.build_record(1.0, [{"t": 0, "src": "one", "text": "iki"}])
    starred_path = ts.save_record(str(tmp_path), starred_rec, subdir="voxis_pin")
    loaded = ts.load_record(starred_path)
    loaded["starred"] = True
    ts.overwrite_record(starred_path, loaded)

    for i in range(3):
        ts.save_record(str(tmp_path), ts.build_record(
            2.0 + i, [{"t": 0, "src": "x", "text": "y"}]), subdir=f"voxis_extra{i}")

    # max_files=3 would normally have to evict the oldest of 4 sessions; the
    # starred one must survive regardless of its age/order.
    pruned = ts.prune_transcripts(str(tmp_path), max_age_days=90, max_files=3)
    assert pruned <= 1
    assert (tmp_path / "voxis_pin").exists()
