"""HistoryMixin.load_session: a pathologically deep session JSON must degrade
to None like any other unreadable record, not crash the calling bridge call
(json's parser recurses per nesting level -- an uncaught RecursionError from
a hand-edited or corrupted transcript file used to propagate straight out).

Also covers star_session: the same traversal/extension guards as
delete_session, plus the read-modify-write round trip on both the current
per-session-folder layout and the legacy flat one.
"""
from app import history_bridge, transcript_store
from app.webui import Bridge


def _bare_bridge(transcripts_dir):
    b = object.__new__(Bridge)
    b.cfg = {"transcript_dir": str(transcripts_dir)}
    b._emit_status = lambda *a, **k: None
    return b


def test_load_session_survives_pathologically_deep_json(tmp_path, monkeypatch):
    monkeypatch.setattr(history_bridge, "legacy_transcripts_dir",
                         lambda: str(tmp_path / "legacy"))
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    bad = transcripts / "voxis_deep.json"
    n = 60000
    bad.write_text('{"a":' * n + "1" + "}" * n, encoding="utf-8")

    b = _bare_bridge(transcripts)
    assert b.load_session("voxis_deep.json") is None


# --- star_session ------------------------------------------------------


def _bridge_with_session(tmp_path, monkeypatch, *, legacy_flat=False):
    monkeypatch.setattr(history_bridge, "legacy_transcripts_dir",
                         lambda: str(tmp_path / "legacy"))
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    b = _bare_bridge(transcripts)
    rec = transcript_store.build_record(1.0, [{"t": 0, "src": "a", "text": "b"}])
    if legacy_flat:
        import json
        path = transcripts / "voxis_flat.json"
        path.write_text(json.dumps(rec), encoding="utf-8")
        return b, "voxis_flat.json"
    path = transcript_store.save_record(str(transcripts), rec, subdir="voxis_nested")
    return b, "voxis_nested.json"


def test_star_session_rejects_path_traversal(tmp_path, monkeypatch):
    b, _ = _bridge_with_session(tmp_path, monkeypatch)
    assert b.star_session("../evil.json", True) is False
    assert b.star_session("sub/evil.json", True) is False


def test_star_session_rejects_wrong_extension(tmp_path, monkeypatch):
    b, _ = _bridge_with_session(tmp_path, monkeypatch)
    assert b.star_session("voxis_nested.txt", True) is False


def test_star_session_rejects_missing_file(tmp_path, monkeypatch):
    b, _ = _bridge_with_session(tmp_path, monkeypatch)
    assert b.star_session("voxis_nowhere.json", True) is False


def test_star_session_round_trip_nested_layout(tmp_path, monkeypatch):
    b, name = _bridge_with_session(tmp_path, monkeypatch, legacy_flat=False)
    assert b.star_session(name, True) is True
    assert b.load_session(name)["starred"] is True
    assert b.star_session(name, False) is True
    assert "starred" not in b.load_session(name)


def test_star_session_round_trip_legacy_flat_layout(tmp_path, monkeypatch):
    b, name = _bridge_with_session(tmp_path, monkeypatch, legacy_flat=True)
    assert b.star_session(name, True) is True
    assert b.load_session(name)["starred"] is True


def test_star_session_invalidates_the_summary_cache(tmp_path, monkeypatch):
    b, name = _bridge_with_session(tmp_path, monkeypatch)
    summaries = {r["file"]: r for r in b.list_sessions()}
    assert summaries[name]["starred"] is False

    assert b.star_session(name, True) is True
    summaries = {r["file"]: r for r in b.list_sessions()}
    assert summaries[name]["starred"] is True


# --- edit_session --------------------------------------------------------


def _bridge_with_multi_turn_session(tmp_path, monkeypatch):
    monkeypatch.setattr(history_bridge, "legacy_transcripts_dir",
                         lambda: str(tmp_path / "legacy"))
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    b = _bare_bridge(transcripts)
    rec = transcript_store.build_record(1.0, [
        {"t": 0.0, "dir": "out", "src": "orijinal bir", "text": "original one",
         "spk": 1},
        {"t": 3.0, "dir": "out", "src": "orijinal iki", "text": "original two"},
    ])
    transcript_store.save_record(str(transcripts), rec, subdir="voxis_edit")
    return b, "voxis_edit.json"


def test_edit_session_rejects_path_traversal(tmp_path, monkeypatch):
    b, _ = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    assert b.edit_session("../evil.json", [{"text": "x"}]) is False


def test_edit_session_rejects_non_list_turns_payload(tmp_path, monkeypatch):
    b, name = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    assert b.edit_session(name, "not a list") is False


def test_edit_session_updates_text_and_src_by_index(tmp_path, monkeypatch):
    b, name = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    ok = b.edit_session(name, [
        {"text": "fixed one", "src": "duzeltilmis bir"},
        {"text": "fixed two"},
    ])
    assert ok is True
    rec = b.load_session(name)
    assert rec["turns"][0]["text"] == "fixed one"
    assert rec["turns"][0]["src"] == "duzeltilmis bir"
    assert rec["turns"][1]["text"] == "fixed two"
    assert rec["turns"][1]["src"] == "orijinal iki"     # untouched: no "src" key in the patch


def test_edit_session_preserves_fields_outside_the_whitelist(tmp_path, monkeypatch):
    b, name = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    b.edit_session(name, [{"text": "fixed one"}, {}])
    rec = b.load_session(name)
    assert rec["turns"][0]["spk"] == 1        # speaker label untouched
    assert rec["turns"][0]["t"] == 0.0        # timing untouched
    assert rec["turns"][1]["text"] == "original two"


def test_edit_session_drops_a_turn_emptied_on_both_sides(tmp_path, monkeypatch):
    b, name = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    b.edit_session(name, [{"text": "", "src": ""}, {}])
    rec = b.load_session(name)
    assert len(rec["turns"]) == 1
    assert rec["turns"][0]["text"] == "original two"


def test_edit_session_ignores_patches_past_the_turn_count(tmp_path, monkeypatch):
    b, name = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    ok = b.edit_session(name, [{}, {}, {"text": "phantom third turn"}])
    assert ok is True
    rec = b.load_session(name)
    assert len(rec["turns"]) == 2


def test_edit_session_export_reflects_the_fix(tmp_path, monkeypatch):
    b, name = _bridge_with_multi_turn_session(tmp_path, monkeypatch)
    b.edit_session(name, [{"text": "fixed one"}, {}])
    out = b.export_session(name, "txt")
    assert out["ok"] is True
    with open(out["path"], encoding="utf-8") as f:
        content = f.read()
    assert "fixed one" in content
    assert "original one" not in content
