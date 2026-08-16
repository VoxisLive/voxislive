"""app.session_summary: prompt building + the generate() call, and the
History-panel wiring (gating, busy-lock, event shape) in history_bridge.py.
"""
import threading

import pytest

import app.history_bridge as history_bridge
import app.session_summary as session_summary
from app.webui import Bridge


def _rec(turns_text=("hello", "world")):
    return {
        "version": 1, "started": 0.0,
        "turns": [{"t": float(i), "dir": "out", "src": "", "text": txt}
                  for i, txt in enumerate(turns_text)],
    }


# --- session_summary.build_prompt / generate --------------------------


def test_build_prompt_raises_on_empty_transcript():
    with pytest.raises(session_summary.SummaryUnavailable):
        session_summary.build_prompt({"turns": []})


def test_build_prompt_includes_turn_text():
    prompt = session_summary.build_prompt(_rec(("Merhaba", "Nasilsin")))
    assert "Merhaba" in prompt
    assert "Nasilsin" in prompt


def test_build_prompt_truncates_to_the_tail_when_oversized(monkeypatch):
    monkeypatch.setattr(session_summary, "MAX_TRANSCRIPT_CHARS", 20)
    rec = _rec(("x" * 15, "y" * 15))
    prompt = session_summary.build_prompt(rec)
    body = prompt.rsplit("---\n", 1)[1]
    assert len(body) == 20
    assert body.endswith("y" * 15)


def test_generate_raises_without_a_key():
    with pytest.raises(session_summary.SummaryUnavailable):
        session_summary.generate(None, _rec())


def test_generate_raises_on_empty_transcript_before_any_network_call():
    with pytest.raises(session_summary.SummaryUnavailable):
        session_summary.generate("fake-key", {"turns": []})


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    """Records every generate_content call; returns/raises what the test wants."""
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append((model, contents))
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)


def _install_fake_client(monkeypatch, models):
    """google.genai.Client(api_key=...) -> an object exposing `.models`."""
    import google.genai as genai_mod
    fake_client = type("FakeClient", (), {"models": models})()
    monkeypatch.setattr(genai_mod, "Client", lambda api_key=None: fake_client)


def test_generate_returns_the_model_text(monkeypatch):
    models = _FakeModels(text="  Kisa bir ozet.  ")
    _install_fake_client(monkeypatch, models)
    out = session_summary.generate("fake-key", _rec())
    assert out == "Kisa bir ozet."
    assert models.calls[0][0] == session_summary.SUMMARY_MODEL


def test_generate_wraps_a_model_exception(monkeypatch):
    models = _FakeModels(exc=RuntimeError("network down"))
    _install_fake_client(monkeypatch, models)
    with pytest.raises(session_summary.SummaryUnavailable):
        session_summary.generate("fake-key", _rec())


def test_generate_raises_on_empty_model_response(monkeypatch):
    models = _FakeModels(text="   ")
    _install_fake_client(monkeypatch, models)
    with pytest.raises(session_summary.SummaryUnavailable):
        session_summary.generate("fake-key", _rec())


# --- history_bridge wiring ---------------------------------------------


def _bare_bridge():
    b = object.__new__(Bridge)
    b.events = []
    b._put_event = b.events.append
    b._summary_lock = threading.Lock()
    b._summary_busy = False
    return b


def test_can_summarize_true_on_oss_build(monkeypatch):
    monkeypatch.setattr(history_bridge, "IS_OFFICIAL_RELEASE", False)
    b = _bare_bridge()
    assert b._can_summarize() is True


def test_can_summarize_false_for_free_tier_on_official_build(monkeypatch):
    monkeypatch.setattr(history_bridge, "IS_OFFICIAL_RELEASE", True)
    b = _bare_bridge()
    b._is_paid = lambda: False
    assert b._can_summarize() is False


def test_can_summarize_true_for_paid_tier_on_official_build(monkeypatch):
    monkeypatch.setattr(history_bridge, "IS_OFFICIAL_RELEASE", True)
    b = _bare_bridge()
    b._is_paid = lambda: True
    assert b._can_summarize() is True


def test_generate_summary_rejected_when_not_allowed(monkeypatch):
    monkeypatch.setattr(history_bridge, "IS_OFFICIAL_RELEASE", True)
    b = _bare_bridge()
    b._is_paid = lambda: False
    out = b.generate_summary("voxis_x.json")
    assert out == {"ok": False, "code": "not_allowed"}


def test_generate_summary_rejected_on_bad_filename(monkeypatch):
    monkeypatch.setattr(history_bridge, "IS_OFFICIAL_RELEASE", False)
    b = _bare_bridge()
    out = b.generate_summary("../evil.json")
    assert out == {"ok": False, "code": "not_found"}


def test_generate_summary_busy_lock(monkeypatch):
    monkeypatch.setattr(history_bridge, "IS_OFFICIAL_RELEASE", False)
    b = _bare_bridge()
    b._summary_busy = True
    out = b.generate_summary("voxis_x.json")
    assert out == {"ok": False, "code": "busy"}


def test_summary_thread_success_writes_record_and_emits_done(tmp_path, monkeypatch):
    monkeypatch.setattr(history_bridge, "legacy_transcripts_dir", lambda: str(tmp_path / "legacy"))
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    import app.transcript_store as ts
    rec = ts.build_record(1.0, [{"t": 0, "src": "a", "text": "hello"}])
    ts.save_record(str(transcripts), rec, subdir="voxis_sum")

    b = _bare_bridge()
    b.cfg = {"transcript_dir": str(transcripts)}
    b._summary_api_key = lambda: "fake-key"
    import app.session_summary as ss
    monkeypatch.setattr(ss, "generate", lambda key, record: "The summary.")

    b._summary_thread("voxis_sum.json")

    states = [e[1]["state"] for e in b.events]
    assert states == ["loading", "done"]
    assert b.events[-1][1]["summary"] == "The summary."
    assert b.load_session("voxis_sum.json")["summary"] == "The summary."
    assert b._summary_busy is False


def test_summary_thread_no_key_emits_error_without_calling_generate(tmp_path, monkeypatch):
    monkeypatch.setattr(history_bridge, "legacy_transcripts_dir", lambda: str(tmp_path / "legacy"))
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    import app.transcript_store as ts
    rec = ts.build_record(1.0, [{"t": 0, "src": "a", "text": "hello"}])
    ts.save_record(str(transcripts), rec, subdir="voxis_nokey")

    b = _bare_bridge()
    b.cfg = {"transcript_dir": str(transcripts)}
    b._summary_api_key = lambda: None
    calls = []
    import app.session_summary as ss
    monkeypatch.setattr(ss, "generate", lambda key, record: calls.append(1))

    b._summary_thread("voxis_nokey.json")
    assert calls == []
    assert [e[1]["state"] for e in b.events] == ["error"]
    assert b.events[0][1]["code"] == "no_key"
    assert "summary" not in b.load_session("voxis_nokey.json")


def test_summary_thread_model_failure_emits_error(tmp_path, monkeypatch):
    monkeypatch.setattr(history_bridge, "legacy_transcripts_dir", lambda: str(tmp_path / "legacy"))
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    import app.transcript_store as ts
    rec = ts.build_record(1.0, [{"t": 0, "src": "a", "text": "hello"}])
    ts.save_record(str(transcripts), rec, subdir="voxis_fail")

    b = _bare_bridge()
    b.cfg = {"transcript_dir": str(transcripts)}
    b._summary_api_key = lambda: "fake-key"
    import app.session_summary as ss

    def _boom(key, record):
        raise ss.SummaryUnavailable("boom")
    monkeypatch.setattr(ss, "generate", _boom)

    b._summary_thread("voxis_fail.json")
    assert [e[1]["state"] for e in b.events] == ["loading", "error"]
    assert b.events[-1][1]["code"] == "failed"
    assert "summary" not in b.load_session("voxis_fail.json")
