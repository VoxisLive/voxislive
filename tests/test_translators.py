"""Characterization tests for the translation-engine session machines.

These lock the *external contract* that must survive the BaseTranslator
consolidation (P0 #6): the drop-oldest queue, carryover ordering across a
rotation, terminal-vs-transient error classification, when `_ready` fires, and
the reconnect/rotation/terminal outcomes of the `_main` loop — all driven with
in-memory fakes, no network. They must pass identically before and after the
refactor.
"""
import asyncio
import time

import pytest

import app.qwen_translator as qwen
import app.translator as gem

ALL_MODULES = (gem, qwen)
ALL_CLASSES = (gem.LiveTranslator, qwen.QwenTranslator)


def _noop(*a, **k):
    pass


def _make(cls, on_status=_noop, on_audio=_noop, on_text=_noop, target="en"):
    return cls("k", target, on_audio=on_audio, on_text=on_text, on_status=on_status)


# --- shared helpers that move into the base class ---------------------------

@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_put_nowait_drops_oldest_and_counts(cls):
    tr = _make(cls)
    tr._queue = asyncio.Queue(maxsize=50)
    for i in range(50):
        tr._queue.put_nowait(bytes([i % 256]) * 4)
    before = gem._USAGE["dropped_frames"]
    tr._put_nowait(b"NEWEST-FRAME")
    assert tr._queue.qsize() == 50                    # still bounded
    assert gem._USAGE["dropped_frames"] == before + 1  # loss is counted
    # The OLDEST frame (index 0) was evicted; the newest is retained.
    drained = []
    while not tr._queue.empty():
        drained.append(tr._queue.get_nowait())
    assert bytes([0]) * 4 not in drained
    assert b"NEWEST-FRAME" in drained


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_carryover_snapshot_and_reinject_preserve_order(cls):
    tr = _make(cls)
    tr._queue = asyncio.Queue(maxsize=50)
    frames = [b"a", b"b", b"c"]
    for f in frames:
        tr._queue.put_nowait(f)
    tr._snapshot_carryover()
    assert tr._carryover == frames          # oldest-first snapshot
    assert tr._queue.empty()                # queue drained into carryover
    tr._reinject_carryover()
    assert tr._carryover == []              # consumed
    out = [tr._queue.get_nowait() for _ in range(3)]
    assert out == frames                     # order preserved into next session


def test_terminal_error_classification_gemini():
    assert gem._is_terminal_error(RuntimeError("Invalid API key"))
    assert gem._is_terminal_error(RuntimeError("Permission denied for this key"))
    assert gem._is_terminal_error(RuntimeError("resource_exhausted"))
    assert not gem._is_terminal_error(RuntimeError("connection reset by peer"))
    assert not gem._is_terminal_error(RuntimeError("429 rate limit"))  # transient


def test_terminal_error_classification_qwen():
    assert qwen._is_terminal_error(RuntimeError("Arrearage: account in debt"))
    assert qwen._is_terminal_error(RuntimeError("AccessDenied"))
    assert not qwen._is_terminal_error(RuntimeError("InvalidParameter: bad lang"))
    # DashScope's account-wide capacity ceiling for this model (2026-08-01/03
    # incidents) — persists for hours, so it fails over immediately instead of
    # grinding through the generic transient-retry budget. Real payload shape:
    # {"code":"COMMON_ERROR","message":"thread pool exhausted max_workers 100"}
    assert qwen._is_terminal_error(
        RuntimeError('{"code":"COMMON_ERROR","message":"thread pool exhausted max_workers 100"}'))


@pytest.mark.parametrize("cls", ALL_CLASSES)
def test_terminal_error_prefers_structured_code(cls):
    mod = {gem.LiveTranslator: gem, qwen.QwenTranslator: qwen}[cls]

    class _E(Exception):
        def __init__(self, code):
            self.code = code

    assert mod._is_terminal_error(_E(403))
    assert not mod._is_terminal_error(_E(429))  # rate-limit is transient
    assert not mod._is_terminal_error(_E(500))


# --- Qwen-specific pure logic ----------------------------------------------

def test_qwen_delta_cumulative_to_increments():
    tr = _make(qwen.QwenTranslator)
    # Cumulative stream: each event repeats the full text so far.
    assert tr._delta("_out_acc", "Hel") == "Hel"
    assert tr._delta("_out_acc", "Hello") == "lo"
    assert tr._delta("_out_acc", "Hello") == ""        # no growth → nothing new
    # A shorter, unrelated string after a reset is emitted whole.
    assert tr._delta("_out_acc", "Bye") == " Bye"


def test_qwen_sentence_boundary_keeps_the_separator():
    """A *.done clears the accumulator, so the next response's first increment
    extends an EMPTY one. Without a separator it returns bare text and webui's
    `_cur_line += text` glues two sentences into one word."""
    tr = _make(qwen.QwenTranslator)
    assert tr._delta("_out_acc", "Bir dakika bekleyelim.") == "Bir dakika bekleyelim."
    # The *.done handler's reset (qwen_translator: response.*.done branch).
    tr._out_acc = ""
    tr._boundary_pending.add("_out_acc")
    assert tr._delta("_out_acc", "Bu arada,") == " Bu arada,"
    # The boundary is spent — mid-sentence growth must not gain a space.
    assert tr._delta("_out_acc", "Bu arada, eğer") == " eğer"


def test_qwen_boundary_survives_a_no_growth_event():
    """A repeated cumulative event emits nothing; the pending boundary must
    still apply to the next event that DOES carry new text."""
    tr = _make(qwen.QwenTranslator)
    tr._out_acc = ""
    tr._boundary_pending.add("_out_acc")
    assert tr._delta("_out_acc", "") == ""
    assert tr._delta("_out_acc", "Tamam.") == " Tamam."


def test_qwen_boundary_does_not_double_space():
    """Qwen sometimes sends its own leading space — never emit two."""
    tr = _make(qwen.QwenTranslator)
    tr._out_acc = ""
    tr._boundary_pending.add("_out_acc")
    assert tr._delta("_out_acc", " Tamam.") == " Tamam."


def test_qwen_rotation_boundary_keeps_the_separator():
    """A 13-min rotation clears the accumulators but not the open caption line
    downstream, so the new session's first increment needs the separator too."""
    tr = _make(qwen.QwenTranslator)
    assert tr._delta("_out_acc", "Önceki oturumun sonu.") == "Önceki oturumun sonu."
    tr._reset_session_state()
    assert tr._delta("_out_acc", "Yeni oturum.") == " Yeni oturum."


def test_qwen_full_event_stream_spaces_every_sentence():
    """End-to-end over the real event shape (delta…delta, done, delta…) —
    the field transcript rendered 'bekleyelim.Bu arada,Eğer giderseniz'."""
    tr = _make(qwen.QwenTranslator)
    line = ""
    stream = [
        ("delta", "Bir"), ("delta", "Bir dakika"), ("delta", "Bir dakika bekleyelim."),
        ("done", "Bir dakika bekleyelim."),
        ("delta", "Bu"), ("delta", "Bu arada,"), ("done", "Bu arada,"),
        ("delta", "Eğer"), ("delta", "Eğer giderseniz"), ("done", "Eğer giderseniz"),
    ]
    for kind, txt in stream:
        inc = tr._delta("_out_acc", txt)
        if inc.strip():
            line += inc
        if kind == "done":                    # mirrors the response.*.done branch
            tr._out_acc = ""
            tr._boundary_pending.add("_out_acc")
    assert line == "Bir dakika bekleyelim. Bu arada, Eğer giderseniz"


def test_give_up_is_logged(caplog):
    """Connection lifecycle used to reach the log file nowhere: base_translator
    did not import logging at all, so a field report of "it reconnected and
    dropped" had zero telemetry behind it (session audit 2026-07-28)."""
    import logging
    tr = _make(qwen.QwenTranslator)
    with caplog.at_level(logging.INFO, logger="voxis"):
        tr._give_up(RuntimeError("arrearage"))
    assert any(r.levelno >= logging.ERROR and "abandoning the reconnect loop" in r.message
               for r in caplog.records)
    assert "arrearage" in caplog.text


def test_give_up_logs_when_a_substitute_engine_takes_over(caplog):
    import logging
    tr = _make(qwen.QwenTranslator)
    tr.on_fatal = lambda exc: True          # a replacement engine handled it
    with caplog.at_level(logging.INFO, logger="voxis"):
        tr._give_up(RuntimeError("quota"))
    assert "a substitute engine took over" in caplog.text


def test_give_up_without_a_substitute_hides_the_raw_upstream_error():
    """No on_fatal (e.g. free/taste tier, 2026-08-12 gate) or a substitute that
    declined to take over must not leak the upstream provider's verbatim error
    text to the user — a DashScope payload like {"code":"COMMON_ERROR",
    "message":"thread pool exhausted max_workers 100"} is not something a user
    should ever see. The raw exc still reaches the log (test_give_up_is_logged),
    just not on_status."""
    from app.i18n import t
    statuses = []
    tr = _make(qwen.QwenTranslator, on_status=statuses.append)
    raw = '{"code":"COMMON_ERROR","message":"thread pool exhausted max_workers 100"}'
    tr._give_up(RuntimeError(raw))
    assert len(statuses) == 1
    assert raw not in statuses[0]
    assert statuses[0] == t("st_engine_gone", name=tr.name)


def test_give_up_when_substitute_declines_also_hides_the_raw_error():
    """on_fatal exists (paid) but itself fails to take over (returns falsy, or
    raises) — same leak risk, same fix applies regardless of tier."""
    statuses = []
    tr = _make(qwen.QwenTranslator, on_status=statuses.append)
    tr.on_fatal = lambda exc: False
    tr._give_up(RuntimeError("upstream said something ugly"))
    assert len(statuses) == 1
    assert "upstream said something ugly" not in statuses[0]


def test_qwen_duplicate_audio_detection():
    import numpy as np
    tr = _make(qwen.QwenTranslator)

    def pcm(seed, n=400):
        rng = np.arange(n) + seed
        return (np.sin(rng) * 8000).astype(np.int16).tobytes()

    a = pcm(0)
    b = pcm(9999)
    # First delta: nothing to compare against.
    assert tr._detect_dup_audio(a) is None
    # Distinct next delta → not a duplicate.
    assert tr._detect_dup_audio(b) is None
    # Exact repeat of the previous delta.
    assert tr._detect_dup_audio(b) == "exact-repeat"
    # Cumulative: previous audio + more.
    assert tr._detect_dup_audio(b) == "exact-repeat"   # b again resets prev=b
    assert tr._detect_dup_audio(b + a) == "cumulative-prefix"
    # Overlap tail: a shorter chunk that is a prefix of the previous one.
    assert tr._detect_dup_audio(b) == "overlap-tail"
    assert tr._dup_audio_count == 4
    assert tr._dup_audio_warned is True


def test_qwen_silence_never_flagged_as_duplicate():
    tr = _make(qwen.QwenTranslator)
    silence = b"\x00\x00" * 400
    assert tr._detect_dup_audio(silence) is None
    assert tr._detect_dup_audio(silence) is None   # identical silence is normal
    assert tr._dup_audio_count == 0


def test_qwen_constructor_normalizes_target_and_clamps_knobs():
    tr = qwen.QwenTranslator("k", "zh-Hans", on_audio=_noop, on_text=_noop,
                             on_status=_noop, clone="bogus", vad_silence_ms=250)
    assert tr.target_lang == "zh"          # BCP-47 → base code
    assert tr.clone == "off"               # invalid clone mode clamped
    assert tr.vad_silence_ms == 250


# --- driven _main loop: Qwen websocket family -------------------------------

class _FakeWS:
    """Minimal async websocket: yields seeded messages then blocks until the
    task is cancelled (mimics a live-but-idle socket)."""

    def __init__(self, incoming=()):
        self._incoming = list(incoming)
        self.sent = []
        self.closed = False

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._incoming:
            return self._incoming.pop(0)
        while True:  # noqa: ASYNC110 -- fake socket idles forever; the test thread is join(timeout=)'d, not signaled
            await asyncio.sleep(0.02)


def _run_ws_translator(cls, connect_impl, ready_msg=None):
    events = []

    class _Driven(cls):
        async def _connect(self):
            return await connect_impl()

    tr = _Driven("k", "en", on_audio=_noop, on_text=_noop,
                 on_status=lambda s: events.append(s))
    tr.start()
    return tr, events


def test_ws_main_sets_ready_only_after_session_event():
    # Qwen connects, then sets _ready only when the server confirms the
    # session (session.created/updated) — NOT on the bare socket open.
    ws = _FakeWS(['{"type":"session.updated"}'])

    async def _connect():
        return ws

    tr, _events = _run_ws_translator(qwen.QwenTranslator, _connect)
    try:
        assert tr.wait_ready(5.0)
    finally:
        tr.stop()
        tr.join(timeout=5.0)
    assert not tr.is_alive()
    assert ws.closed


def test_ws_main_terminal_error_breaks_without_retry(caplog):
    import logging
    connects = []
    ws = _FakeWS(['{"type":"error","error":"unauthorized"}'])

    async def _connect():
        connects.append(1)
        return ws

    with caplog.at_level(logging.INFO, logger="voxis"):
        tr, _events = _run_ws_translator(qwen.QwenTranslator, _connect)
        tr.join(timeout=6.0)
    assert not tr.is_alive()
    assert len(connects) == 1  # terminal → no reconnect spin
    # The classification that ended the session must be in the log, not just on screen.
    assert "terminal error, not retrying" in caplog.text


def test_terminal_error_retries_once_via_fallback_pool_before_giving_up():
    # DashScope's "thread pool exhausted" (this model's account-wide capacity
    # ceiling — 2026-08-01/03 incidents) is terminal (see _TERMINAL_PHRASES),
    # but a server-provided fallback credential for a SIBLING pool
    # (session_key.go's qwenFallbackCredentials) is worth one immediate retry
    # BEFORE an on_fatal swap to Gemini — a session that only lost ONE pool
    # should stay on the higher-quality engine instead of downgrading.
    connects = []
    healthy = _FakeWS(['{"type":"session.updated"}'])

    class _Driven(qwen.QwenTranslator):
        async def _connect(self):
            connects.append(self.api_key)
            if len(connects) == 1:
                return _FakeWS(['{"type":"error",'
                               '"error":"thread pool exhausted max_workers 100"}'])
            return healthy

    fatal_calls = []
    tr = _Driven("PRIMARY", "en", on_audio=_noop, on_text=_noop, on_status=_noop,
                fallback={"key": "FALLBACK", "model": "m2", "workspace": "w2"})
    tr.on_fatal = lambda exc: fatal_calls.append(exc) or True
    tr.start()
    try:
        # READY_ON_CONNECT fires on the FIRST (doomed) connect too, so wait for
        # the fallback reconnect itself rather than trusting wait_ready() timing.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and len(connects) < 2:
            time.sleep(0.02)
        assert connects == ["PRIMARY", "FALLBACK"], "must retry exactly once, on the new credential"
        assert tr.wait_ready(5.0), "the fallback pool must serve the session"
    finally:
        tr.stop()
        tr.join(timeout=5.0)
    assert not tr.is_alive()
    assert connects == ["PRIMARY", "FALLBACK"]  # no third attempt after healing
    assert tr.model == "m2" and tr.workspace == "w2"
    assert not fatal_calls  # never abandoned the engine — the fallback pool served it


def test_terminal_error_on_fallback_pool_also_gives_up_no_third_attempt():
    # The fallback is used AT MOST ONCE per translator lifetime: if it ALSO
    # dies with the same terminal signature, the session must give up (→
    # on_fatal → Gemini) rather than loop forever hunting for a healthy pool.
    connects = []

    class _Driven(qwen.QwenTranslator):
        async def _connect(self):
            connects.append(self.api_key)
            return _FakeWS(['{"type":"error",'
                           '"error":"thread pool exhausted max_workers 100"}'])

    fatal_calls = []
    tr = _Driven("PRIMARY", "en", on_audio=_noop, on_text=_noop, on_status=_noop,
                fallback={"key": "FALLBACK", "model": "m2", "workspace": "w2"})
    tr.on_fatal = lambda exc: fatal_calls.append(exc) or True
    tr.start()
    tr.join(timeout=6.0)
    assert not tr.is_alive()
    assert connects == ["PRIMARY", "FALLBACK"]  # exactly 2 attempts, no more
    assert len(fatal_calls) == 1                 # gave up once both pools failed


def test_asr_failures_alone_still_arm_the_no_output_watchdog():
    # Field regression (CORFO meeting, 2026-07-29): DashScope answered every
    # utterance with input_audio_transcription.failed and produced no output.
    # Those frames reset the stall watchdog, and the .failed branch used not to
    # mark input — so the no-output watchdog stayed disarmed and the session sat
    # dead for 12m52s with the meter running. A .failed-ONLY stream must still
    # force a self-heal reconnect. INPUT_RECENT_SECONDS is left at its real
    # value here: the point is that .failed refreshes _last_input_ts.
    connects = []
    failed = ('{"type":"conversation.item.input_audio_transcription.failed",'
              '"error":{"type":"transcription_error",'
              '"code":"UNEXPECTED_ASR_ERROR"}}')
    first = _FakeWS([failed, failed, failed])

    class _Driven(qwen.QwenTranslator):
        NO_OUTPUT_WARN_SECONDS = 0.05
        NO_OUTPUT_ROTATE_SECONDS = 0.1

        async def _connect(self):
            connects.append(1)
            # Only the first socket errors; the healed session is idle, so the
            # watchdog disarms instead of spinning further reconnects.
            return first if len(connects) == 1 else _FakeWS()

    tr = _Driven("k", "en", on_audio=_noop, on_text=_noop, on_status=_noop)
    tr.start()
    try:
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and len(connects) < 2:
            time.sleep(0.05)
        assert len(connects) >= 2, "ASR errors alone left the session black-holed"
    finally:
        tr.stop()
        tr.join(timeout=5.0)
    assert not tr.is_alive()


def test_no_output_watchdog_self_heals_by_reconnecting():
    # Input transcription is flowing but the engine emits NO output — the
    # Beta-off→Gemini "translation stops" failure. The watchdog must escalate
    # from warn-only to a forced reconnect (self-heal), not sit dead. Thresholds
    # shrunk so the stall trips in one sender tick.
    connects = []
    first = _FakeWS(['{"type":"conversation.item.input_audio_transcription.'
                     'completed","transcript":"hola"}'])

    class _Driven(qwen.QwenTranslator):
        NO_OUTPUT_WARN_SECONDS = 0.05
        NO_OUTPUT_ROTATE_SECONDS = 0.1
        INPUT_RECENT_SECONDS = 100.0

        async def _connect(self):
            connects.append(1)
            # Only the first socket carries input; the healed session is idle, so
            # the watchdog disarms and does not spin further reconnects.
            return first if len(connects) == 1 else _FakeWS()

    events = []
    tr = _Driven("k", "en", on_audio=_noop, on_text=_noop,
                 on_status=lambda s: events.append(s))
    tr.start()
    try:
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and len(connects) < 2:
            time.sleep(0.05)
        assert len(connects) >= 2  # the stall forced a reconnect
        # Status text is localized (st_noout_reconnect) — pin via the i18n key.
        from app.i18n import t
        expected = t("st_noout_reconnect", name=tr.name,
                     s=int(_Driven.NO_OUTPUT_ROTATE_SECONDS))
        assert any(e == expected for e in events)
    finally:
        tr.stop()
        tr.join(timeout=5.0)
    assert not tr.is_alive()


def test_ws_main_transient_error_retries_then_succeeds(caplog):
    import logging
    calls = {"n": 0}
    ws = _FakeWS(['{"type":"session.updated"}'])

    async def _connect():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("temporary reset")
        return ws

    with caplog.at_level(logging.INFO, logger="voxis"):
        tr, _events = _run_ws_translator(qwen.QwenTranslator, _connect)
        try:
            assert tr.wait_ready(8.0)   # succeeds on the 2nd attempt after backoff
            assert calls["n"] == 2
        finally:
            tr.stop()
            tr.join(timeout=6.0)
    assert not tr.is_alive()
    # Both the retry and the recovery are traceable after the fact.
    assert "transient error" in caplog.text and "temporary reset" in caplog.text
    assert "session connected" in caplog.text


# --- driven _main loop: Gemini SDK family -----------------------------------

class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeSession:
    def __init__(self, responses=()):
        self._responses = list(responses)
        self.sent = []

    async def send_realtime_input(self, audio=None):
        self.sent.append(audio)

    async def receive(self):
        for r in self._responses:
            yield r
        while True:  # noqa: ASYNC110 -- fake socket idles forever; the test thread is join(timeout=)'d, not signaled
            await asyncio.sleep(0.02)


class _FakeConnectCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    def __init__(self, sessions):
        self._sessions = list(sessions)
        outer = self

        class _Live:
            def connect(self, model=None, config=None):
                s = outer._sessions.pop(0) if outer._sessions else _FakeSession()
                return _FakeConnectCM(s)

        self.aio = _Obj(live=_Live())


def _patch_gemini_client(monkeypatch, sessions):
    monkeypatch.setattr(gem.genai, "Client",
                        lambda **kw: _FakeClient(sessions))


def test_gemini_main_sets_ready_on_connect(monkeypatch):
    # Gemini sets _ready right after the connect context opens (no separate
    # server 'session live' event), unlike the websocket engines.
    _patch_gemini_client(monkeypatch, [_FakeSession()])
    tr = gem.LiveTranslator("k", "en", on_audio=_noop, on_text=_noop,
                            on_status=_noop)
    tr.start()
    try:
        assert tr.wait_ready(5.0)
    finally:
        tr.stop()
        tr.join(timeout=5.0)
    assert not tr.is_alive()


def test_gemini_goaway_rotates_and_keeps_resume_handle(monkeypatch):
    sru = _Obj(resumable=True, new_handle="H1")
    resp_resume = _Obj(session_resumption_update=sru, go_away=None,
                       server_content=None)
    resp_goaway = _Obj(session_resumption_update=None, go_away=_Obj(),
                       server_content=None)
    s1 = _FakeSession([resp_resume, resp_goaway])
    s2 = _FakeSession()
    _patch_gemini_client(monkeypatch, [s1, s2])

    tr = gem.LiveTranslator("k", "en", on_audio=_noop, on_text=_noop,
                            on_status=_noop)
    tr.start()
    try:
        # The GoAway on session 1 forces a seamless rotation; the resume handle
        # captured from the resumption update survives into session 2.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and tr._resume_handle != "H1":
            time.sleep(0.02)
        assert tr._resume_handle == "H1"
    finally:
        tr.stop()
        tr.join(timeout=5.0)
    assert not tr.is_alive()


# --- per-response audio/text accounting -------------------------------------

def _resp_translator():
    tr = _make(qwen.QwenTranslator)
    tr._resp, tr._cur_resp = {}, None
    tr._silent_resp = tr._silent_chars = 0
    return tr


def test_response_with_text_but_no_audio_is_reported(caplog):
    """Two recorded sessions captioned more than they spoke. Aggregate counts
    could not say WHICH text was never voiced; pairing audio to text per
    response can."""
    import logging
    tr = _resp_translator()
    tr._note_response({"response_id": "r1"}, chars=40)
    tr._note_response({"response_id": "r1"}, audio=9600)
    tr._note_response({"response_id": "r2"}, chars=55)      # captioned, never voiced
    with caplog.at_level(logging.INFO, logger="voxis"):
        tr._flush_response_stats()
    assert "NO AUDIO for 1 response" in caplog.text
    assert tr._silent_resp == 1 and tr._silent_chars == 55


def test_a_response_is_judged_only_at_session_end():
    """Audio and text for one response interleave in no guaranteed order, so a
    response judged at its own .done would report silence that had merely not
    arrived yet."""
    tr = _resp_translator()
    tr._note_response({"response_id": "r1"}, chars=30)
    assert tr._silent_resp == 0          # nothing concluded yet
    tr._note_response({"response_id": "r1"}, audio=4800)
    tr._flush_response_stats()
    assert tr._silent_resp == 0


def test_events_without_a_response_id_book_against_the_current_one():
    """response_id rides the *.done events for certain; on deltas it is
    best-effort."""
    tr = _resp_translator()
    tr._note_response({"response_id": "r7"}, chars=10)
    tr._note_response({}, audio=2400)                # no id on this delta
    tr._flush_response_stats()
    assert tr._silent_resp == 0, "the audio must land on r7, not be dropped"


def test_audio_only_response_is_not_reported():
    """Audio with no caption is not the defect being hunted."""
    tr = _resp_translator()
    tr._note_response({"response_id": "r1"}, audio=4800)
    tr._flush_response_stats()
    assert tr._silent_resp == 0


def test_stats_reset_between_sessions_but_totals_survive():
    tr = _resp_translator()
    tr._note_response({"response_id": "a"}, chars=20)
    tr._flush_response_stats()
    assert tr._resp == {} and tr._silent_chars == 20
    tr._note_response({"response_id": "b"}, chars=5)
    tr._flush_response_stats()
    assert tr._silent_resp == 2 and tr._silent_chars == 25


def test_thread_exit_hook_judges_the_final_session():
    """A rotation-time flush only ever sees the sessions BEFORE the last one."""
    tr = _resp_translator()
    tr._note_response({"response_id": "last"}, chars=33)
    tr._on_thread_exit()
    assert tr._silent_chars == 33


def test_base_thread_exit_hook_is_a_noop_by_default():
    tr = _make(gem.LiveTranslator)
    tr._on_thread_exit()          # must not raise
