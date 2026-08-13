"""HistoryMixin.load_session: a pathologically deep session JSON must degrade
to None like any other unreadable record, not crash the calling bridge call
(json's parser recurses per nesting level -- an uncaught RecursionError from
a hand-edited or corrupted transcript file used to propagate straight out).
"""
from app import history_bridge
from app.webui import Bridge


def _bare_bridge(transcripts_dir):
    b = object.__new__(Bridge)
    b.cfg = {"transcript_dir": str(transcripts_dir)}
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
