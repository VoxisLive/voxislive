"""The silent-first-minute defences and the session-outcome event.

Measured 2026-07-31 over every recorded session (PB usage_events, session_id
level): 40% of Windows-app sessions end under 30 s, 59% under a minute, and 71%
of those short sessions are followed by ANOTHER attempt a median 14 s later —
people were retrying, not losing interest. Two blind spots made that impossible
to act on:

  * the app said nothing when NO audio reached the capture at all, which is what
    a user gets when nothing is playing or when they speak into their microphone
    expecting Video mode to translate it (both reported from the field);
  * the funnel stopped at session_live, so an abandoned session and a completed
    one looked identical, and the first-audio latency RTTEstimator already
    measured for the UI was never reported anywhere.

These pin the parts a refactor could silently undo: the notice fires once, only
in video mode, only when nothing was heard; and session_end carries the outcome
with reason precedence intact.
"""
from app import pipeline as P


class _FakeRTT:
    def __init__(self, first_audio=None, speech=False):
        self.first_audio_seconds = first_audio
        self.speech_seen = speech


def _controller():
    c = P.ModeController.__new__(P.ModeController)
    c._no_input_notified = False
    c._capture_dead_notified = False
    c._session_mode = "video"
    c._session_id = "sid1234"
    c._session_start = P.time.monotonic() - 60.0
    c._quota_exhausted = P.threading.Event()
    c._session_failed = P.threading.Event()
    c.said = []
    c.on_status = c.said.append
    return c


def _incoming(peak=0.0, speech=False, first_audio=None):
    inc = P.IncomingPipeline.__new__(P.IncomingPipeline)
    inc.peak_input_level = peak
    inc._rtt = _FakeRTT(first_audio, speech)
    inc._engine = "qwen"
    return inc


# ── input metering ──────────────────────────────────────────────────────────
def test_peak_input_level_survives_the_meters_decay():
    """The instantaneous meter is smoothed with a slow release and dips to ~0 in
    an ordinary pause; only the peak can answer 'did ANY audio ever arrive'."""
    import numpy as np

    pipe = P.IncomingPipeline.__new__(P.IncomingPipeline)
    pipe.input_level = 0.0
    pipe._recorder = None
    pipe._source = type("S", (), {"feed": staticmethod(lambda _c: None)})()

    for _ in range(20):
        pipe._ingest_input(np.full(512, 0.4, dtype=np.float32))
    loud = pipe.peak_input_level
    assert loud > P.ModeController.INPUT_SILENT_LEVEL
    for _ in range(200):
        pipe._ingest_input(np.zeros(512, dtype=np.float32))
    assert pipe.input_level < P.ModeController.INPUT_SILENT_LEVEL  # decayed away
    assert pipe.peak_input_level == loud                          # peak remembered


# ── no-input notice ─────────────────────────────────────────────────────────
def test_no_input_notice_fires_once_when_nothing_was_heard(monkeypatch):
    c = _controller()
    inc = _incoming(peak=0.0, speech=False)
    monkeypatch.setattr(c, "incoming", lambda: inc, raising=False)

    c._maybe_warn_no_input()
    c._maybe_warn_no_input()   # a second heartbeat must not repeat it
    assert len(c.said) == 1
    assert c.said[0] == P.t("st_no_input_audio")


def test_no_input_notice_stays_quiet_when_audio_arrived(monkeypatch):
    for inc in (_incoming(peak=0.5, speech=False),      # signal, no speech yet
                _incoming(peak=0.0, speech=True)):      # speech seen
        c = _controller()
        monkeypatch.setattr(c, "incoming", lambda inc=inc: inc, raising=False)
        c._maybe_warn_no_input()
        assert c.said == []
        assert c._no_input_notified is True  # armed off, never asks again


def test_no_input_notice_never_fires_in_meeting(monkeypatch):
    """Total silence on a meeting's incoming leg is the normal state of a call
    nobody is talking in yet (a muted remote party is digital zero), so the same
    notice there would cry wolf during real calls."""
    c = _controller()
    c._session_mode = "meeting"
    monkeypatch.setattr(c, "incoming", lambda: _incoming(), raising=False)
    c._maybe_warn_no_input()
    assert c.said == []


def test_no_input_notice_waits_for_the_grace_window(monkeypatch):
    c = _controller()
    c._session_start = P.time.monotonic()   # just started
    monkeypatch.setattr(c, "incoming", lambda: _incoming(), raising=False)
    c._maybe_warn_no_input()
    assert c.said == []
    assert c._no_input_notified is False    # not consumed — it may still fire


# ── session_end ─────────────────────────────────────────────────────────────
def _capture_events(monkeypatch):
    sent = []
    monkeypatch.setattr(P.voxis_client, "report_event_async",
                        lambda ev, sid, meta=None: sent.append((ev, sid, meta)))
    return sent


def test_session_end_carries_the_outcome(monkeypatch):
    sent = _capture_events(monkeypatch)
    c = _controller()
    monkeypatch.setattr(c, "incoming",
                        lambda: _incoming(peak=0.31, speech=True, first_audio=4.2),
                        raising=False)
    monkeypatch.setattr(c, "current_engine", lambda: "qwen", raising=False)

    c._report_session_end("user_stop")

    assert len(sent) == 1
    ev, sid, meta = sent[0]
    assert (ev, sid) == ("session_end", "sid1234")
    assert meta["reason"] == "user_stop"
    assert meta["mode"] == "video"
    assert meta["first_audio_s"] == 4.2
    assert meta["speech_seen"] is True
    assert meta["seconds"] >= 59
    # PII-free by construction: labels, numbers and booleans only.
    assert set(meta) == {"mode", "reason", "seconds", "first_audio_s",
                         "speech_seen", "peak_level", "engine"}


def test_session_end_reports_the_never_heard_a_word_case(monkeypatch):
    """first_audio_s None + speech_seen False is the whole point: it separates
    'nothing was playing' from 'audio flowed but no translation came back'."""
    sent = _capture_events(monkeypatch)
    c = _controller()
    monkeypatch.setattr(c, "incoming", lambda: _incoming(), raising=False)
    monkeypatch.setattr(c, "current_engine", lambda: "", raising=False)

    c._report_session_end("user_stop")

    meta = sent[0][2]
    assert meta["first_audio_s"] is None
    assert meta["speech_seen"] is False


def test_session_end_reason_precedence(monkeypatch):
    """A real outcome outranks the caller's label: quota beats error beats a
    dead capture beats whatever stop() was called with."""
    cases = [
        ("quota", lambda c: c._quota_exhausted.set()),
        ("error", lambda c: c._session_failed.set()),
        ("capture_lost", lambda c: setattr(c, "_capture_dead_notified", True)),
    ]
    for expected, arm in cases:
        sent = _capture_events(monkeypatch)
        c = _controller()
        arm(c)
        monkeypatch.setattr(c, "incoming", lambda: _incoming(), raising=False)
        monkeypatch.setattr(c, "current_engine", lambda: "", raising=False)
        c._report_session_end("restart")
        assert sent[0][2]["reason"] == expected


def test_session_end_is_silent_without_a_live_session(monkeypatch):
    """A start that never came up already reports session_error; emitting an end
    for it would double-count the same failure."""
    sent = _capture_events(monkeypatch)
    c = _controller()
    c._session_id = None
    c._report_session_end("user_stop")
    assert sent == []


def test_error_class_names_the_unclassified(monkeypatch):
    """The `other` bucket swallowed 82 of 143 recorded start failures. Existing
    labels must keep their exact strings (historical rows stay comparable) and
    the fallback must carry the exception TYPE — never its message."""
    assert P._event_error_class(OSError("PaError -9999")) == "audio_device"
    assert P._event_error_class(RuntimeError("wait_ready timeout")) == "translator_timeout"
    assert P._event_error_class(ImportError("no comtypes")) == "os_import"
    assert P._event_error_class(OSError("getaddrinfo failed")) == "network"
    assert P._event_error_class(RuntimeError("401 unauthorized")) == "auth_key"
    assert P._event_error_class(ValueError("output device not found")) == "no_device"

    class OddFault(Exception):
        pass

    label = P._event_error_class(OddFault("C:/Users/someone/secret.wav missing"))
    assert label == "other:OddFault"
    assert "someone" not in label and "secret" not in label
