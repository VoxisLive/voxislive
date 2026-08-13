"""History listing must not re-open every session JSON on each call.

list_records parses a whole record to read four header fields, a turn count and
an 80-char preview. Parsing is cheap once the file is in the page cache; the cost
is the per-file OPEN on a cold one (measured ~14 ms per file on Windows, where
the AV filter sits in the path), and it is paid for BOTH the active and legacy
transcript dirs. At the 500-file prune cap that is seconds on the first History
open after launch. Summaries are now cached and revalidated by (mtime_ns, size).
"""
import json
import os
import time

import pytest

from app import transcript_store


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path_factory, monkeypatch):
    """Every test starts with an empty cache AND its own on-disk index, so the
    suite never reads or writes the real %APPDATA%\\Voxis index."""
    idx = tmp_path_factory.mktemp("idx") / "transcript_index.json"
    monkeypatch.setattr(transcript_store, "_index_path", lambda: str(idx))
    monkeypatch.setattr(transcript_store, "_SUMMARY_CACHE", {})
    monkeypatch.setattr(transcript_store, "_INDEX_LOADED", False)
    monkeypatch.setattr(transcript_store, "_INDEX_DIRTY", False)
    yield idx


def _write(directory, stamp, turns):
    path = os.path.join(directory, f"voxis_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"started": 1000.0 + int(stamp), "started_iso": "iso",
                   "mode": "video", "target_in": "tr", "target_out": "en",
                   "turns": turns}, f)
    return path


def test_second_listing_reads_no_files(tmp_path, monkeypatch):
    d = str(tmp_path)
    _write(d, "1", [{"text": "bir"}])
    _write(d, "2", [{"text": "iki"}])

    first = transcript_store.list_records(d)
    assert [r["preview"] for r in first] == ["iki", "bir"]

    opened = []
    real = transcript_store.load_record
    monkeypatch.setattr(transcript_store, "load_record",
                        lambda p: opened.append(p) or real(p))

    second = transcript_store.list_records(d)
    assert second == first
    assert opened == [], "cache hit must not re-open the record"


def test_a_rewritten_record_is_re_read(tmp_path):
    d = str(tmp_path)
    path = _write(d, "1", [{"text": "before"}])
    assert transcript_store.list_records(d)[0]["preview"] == "before"

    # Same path, new content. Bump mtime explicitly so the test does not depend
    # on the filesystem's timestamp resolution.
    _write(d, "1", [{"text": "after"}])
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    assert transcript_store.list_records(d)[0]["preview"] == "after"


def test_same_size_edit_is_still_detected(tmp_path):
    """Size alone would miss an in-place edit; mtime_ns is part of the key."""
    d = str(tmp_path)
    path = _write(d, "1", [{"text": "aaa"}])
    assert transcript_store.list_records(d)[0]["preview"] == "aaa"

    _write(d, "1", [{"text": "bbb"}])          # identical length
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    assert transcript_store.list_records(d)[0]["preview"] == "bbb"


def test_deleted_record_disappears_even_though_it_was_cached(tmp_path):
    d = str(tmp_path)
    path = _write(d, "1", [{"text": "gone"}])
    _write(d, "2", [{"text": "stays"}])
    assert len(transcript_store.list_records(d)) == 2

    os.remove(path)
    transcript_store.invalidate_summary_cache(path)
    remaining = transcript_store.list_records(d)
    assert [r["preview"] for r in remaining] == ["stays"]


def test_stale_entry_cannot_resurrect_a_deleted_file(tmp_path):
    """Even WITHOUT an explicit invalidation: the listing walks the directory, so
    a file that is gone is simply never looked up."""
    d = str(tmp_path)
    path = _write(d, "1", [{"text": "gone"}])
    transcript_store.list_records(d)
    os.remove(path)
    assert transcript_store.list_records(d) == []


def test_caller_mutation_cannot_poison_the_cache(tmp_path):
    """webui.list_sessions merges these dicts across dirs; a mutation there must
    not reach back into the cached copy."""
    d = str(tmp_path)
    _write(d, "1", [{"text": "orijinal"}])

    first = transcript_store.list_records(d)
    first[0]["preview"] = "TAMPERED"
    first[0]["file"] = "TAMPERED.json"

    second = transcript_store.list_records(d)
    assert second[0]["preview"] == "orijinal"
    assert second[0]["file"] == "voxis_1.json"


def test_pruning_clears_the_cache(tmp_path):
    d = str(tmp_path)
    old = _write(d, "1", [{"text": "old"}])
    _write(d, "2", [{"text": "new"}])
    transcript_store.list_records(d)

    ancient = time.time() - 200 * 86400
    os.utime(old, (ancient, ancient))
    assert transcript_store.prune_transcripts(d, max_age_days=90) == 1
    assert [r["preview"] for r in transcript_store.list_records(d)] == ["new"]


def test_index_survives_a_restart(tmp_path, _isolated_cache, monkeypatch):
    """THE point of persisting it: an in-process dict alone still pays the full
    cold cost on the first History open of every launch, which is the case that
    actually hurts. Simulate a restart by clearing the in-memory state and
    re-loading from the index file."""
    d = str(tmp_path)
    _write(d, "1", [{"text": "bir"}])
    _write(d, "2", [{"text": "iki"}])
    first = transcript_store.list_records(d)
    assert os.path.exists(_isolated_cache), "index was never written"

    # "Restart": memory gone, index file kept.
    monkeypatch.setattr(transcript_store, "_SUMMARY_CACHE", {})
    monkeypatch.setattr(transcript_store, "_INDEX_LOADED", False)
    opened = []
    real = transcript_store.load_record
    monkeypatch.setattr(transcript_store, "load_record",
                        lambda p: opened.append(p) or real(p))

    assert transcript_store.list_records(d) == first
    assert opened == [], "a fresh process re-opened records the index already had"


def test_corrupt_index_falls_back_to_reading_records(tmp_path, _isolated_cache, monkeypatch):
    """The index is a cache, never data: a truncated or hand-edited one must
    degrade to the old behaviour, not break History."""
    d = str(tmp_path)
    _write(d, "1", [{"text": "bir"}])
    _isolated_cache.parent.mkdir(parents=True, exist_ok=True)
    _isolated_cache.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(transcript_store, "_SUMMARY_CACHE", {})
    monkeypatch.setattr(transcript_store, "_INDEX_LOADED", False)

    assert [r["preview"] for r in transcript_store.list_records(d)] == ["bir"]


def test_pathologically_deep_index_falls_back_to_reading_records(
        tmp_path, _isolated_cache, monkeypatch):
    # json's parser recurses per nesting level -- an uncaught RecursionError
    # from a deeply nested index file used to propagate instead of degrading
    # like any other corrupt cache (the index is a cache, never data).
    d = str(tmp_path)
    _write(d, "1", [{"text": "bir"}])
    _isolated_cache.parent.mkdir(parents=True, exist_ok=True)
    n = 60000
    _isolated_cache.write_text('{"a":' * n + "1" + "}" * n, encoding="utf-8")
    monkeypatch.setattr(transcript_store, "_SUMMARY_CACHE", {})
    monkeypatch.setattr(transcript_store, "_INDEX_LOADED", False)

    assert [r["preview"] for r in transcript_store.list_records(d)] == ["bir"]


def test_index_entries_of_the_wrong_shape_are_skipped(tmp_path, _isolated_cache, monkeypatch):
    d = str(tmp_path)
    path = _write(d, "1", [{"text": "gercek"}])
    _isolated_cache.parent.mkdir(parents=True, exist_ok=True)
    escaped_path = os.path.abspath(path).replace("\\", "\\\\")
    _isolated_cache.write_text(
        f'{{"{escaped_path}": "not-a-list", "other": [1, 2]}}',
        encoding="utf-8")
    monkeypatch.setattr(transcript_store, "_SUMMARY_CACHE", {})
    monkeypatch.setattr(transcript_store, "_INDEX_LOADED", False)

    assert [r["preview"] for r in transcript_store.list_records(d)] == ["gercek"]


def test_index_drops_entries_whose_file_is_gone(tmp_path, _isolated_cache):
    import json as _json
    d = str(tmp_path)
    gone = _write(d, "1", [{"text": "gone"}])
    _write(d, "2", [{"text": "stays"}])
    transcript_store.list_records(d)

    os.remove(gone)
    transcript_store.invalidate_summary_cache(gone)
    written = _json.loads(_isolated_cache.read_text(encoding="utf-8"))
    assert os.path.abspath(gone) not in written
    assert len(written) == 1


def test_unwritable_index_never_breaks_the_listing(tmp_path, monkeypatch):
    d = str(tmp_path)
    _write(d, "1", [{"text": "bir"}])
    monkeypatch.setattr(transcript_store, "_index_path",
                        lambda: os.path.join(str(tmp_path), "no", "such", "\0bad"))
    monkeypatch.setattr(transcript_store, "_SUMMARY_CACHE", {})
    monkeypatch.setattr(transcript_store, "_INDEX_LOADED", False)

    assert [r["preview"] for r in transcript_store.list_records(d)] == ["bir"]


def test_nested_and_flat_layouts_are_both_cached(tmp_path):
    """The per-session-folder layout (1.0.28+) and the legacy flat one share the
    cache; neither may shadow the other."""
    d = str(tmp_path)
    _write(d, "1", [{"text": "flat"}])
    nested = os.path.join(d, "voxis_2")
    os.makedirs(nested)
    _write(nested, "2", [{"text": "nested"}])

    first = transcript_store.list_records(d)
    assert sorted(r["preview"] for r in first) == ["flat", "nested"]
    assert transcript_store.list_records(d) == first
