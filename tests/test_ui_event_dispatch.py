"""UI event delivery: identity-based dedupe, and nothing blocking on the
translator's receive thread.

Two regressions are pinned here.

1. The push channel used to call pywebview's evaluate_js INLINE from _put_event.
   That call is synchronous on EdgeChromium (it Invokes the WebView2 UI thread
   and blocks on a semaphore), and _put_event runs on the translator's receive
   loop -- the SAME loop that delivers translated audio on both Gemini and Qwen.
   It must never block there.

2. The UI deduped the push copy against the poll copy by CONTENT, which cannot
   distinguish a duplicate DELIVERY from a genuinely repeated EVENT. Identical
   consecutive caption deltas lost the second one, and the fixed-payload events
   (quota_refresh / quota_wall / review / daily_wall all carry a constant null)
   could only fire once per dedupe window.
"""
import queue
import threading
import time

from app.webui import Bridge


class _SlowWindow:
    """Stands in for a busy WebView2: every evaluate_js takes 200 ms."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def evaluate_js(self, code):
        time.sleep(0.2)
        with self.lock:
            self.calls.append(code)


def _bare_bridge() -> Bridge:
    """A Bridge with only the event plumbing -- no config, audio or webview."""
    b = Bridge.__new__(Bridge)
    b._events = queue.Queue(maxsize=400)
    b._push_q = queue.Queue(maxsize=400)
    b._event_seq = 0
    b._seq_lock = threading.Lock()
    b._dispatch_stop = threading.Event()
    b._obs_pending = None
    b._obs_lock = threading.Lock()
    b._last_obs_write = None
    b._main_window = None
    return b


def _drain(q):
    out = []
    try:
        while True:
            out.append(q.get_nowait())
    except queue.Empty:
        pass
    return out


def test_put_event_never_blocks_on_the_webview():
    """The regression that mattered: a 200 ms JS frame must not be 200 ms of
    stalled receive thread. Ten events would have cost 2 s inline."""
    b = _bare_bridge()
    b._main_window = _SlowWindow()
    thread = threading.Thread(target=b._dispatch_loop, daemon=True)
    thread.start()
    try:
        t0 = time.perf_counter()
        for i in range(10):
            b._put_event(("trans", f"tok{i}", False, None, 0.0))
        elapsed = time.perf_counter() - t0
    finally:
        b._dispatch_stop.set()
        thread.join(timeout=3.0)
    assert elapsed < 0.15, f"_put_event blocked for {elapsed:.3f}s"


def test_both_channels_carry_every_event_with_one_identity():
    b = _bare_bridge()
    b._put_event(("status", "hello", None))
    b._put_event(("status", "hello", None))     # deliberately identical payload

    pushed, polled = _drain(b._push_q), _drain(b._events)
    assert len(pushed) == 2 and len(polled) == 2
    assert [m["seq"] for m in pushed] == [1, 2]
    assert pushed == polled                      # same objects, same identities
    assert pushed[0]["ev"] == ["status", "hello", None]


def test_repeated_identical_events_get_distinct_sequence_numbers():
    """Content dedupe would have collapsed these; identity dedupe must not.
    Covers both a repeated caption delta and the constant-payload events."""
    b = _bare_bridge()
    for _ in range(3):
        b._put_event(("trans", " ", False, None, 0.0))
    for _ in range(2):
        b._put_event(("quota_refresh", None))

    msgs = _drain(b._events)
    assert len(msgs) == 5
    assert len({m["seq"] for m in msgs}) == 5, "duplicate seq -> the UI drops one"


def test_sequence_is_monotonic_under_concurrent_producers():
    """Meeting mode runs two receive threads into _put_event at once, so seq
    minting must be atomic -- a collision would make the UI drop a real event.

    800 events into a 400-slot queue: the oldest half is dropped by design, so
    what survives is the CONTIGUOUS TAIL 401..800. That is the assertion -- no
    duplicates, no gaps, and the newest kept."""
    b = _bare_bridge()
    total = 800

    def produce():
        for _ in range(total // 4):
            b._put_event(("trans", "x", False, None, 0.0))

    threads = [threading.Thread(target=produce) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert b._event_seq == total, "a seq was lost or reused under contention"
    seqs = sorted(m["seq"] for m in _drain(b._events))
    assert len(set(seqs)) == len(seqs), "duplicate seq -> the UI drops a real event"
    assert seqs == list(range(total - 400 + 1, total + 1))


def test_dispatcher_survives_a_dead_window():
    """A window torn down mid-session must not kill the dispatcher: the poll
    backstop still has to receive everything after it."""
    class _Dead:
        def evaluate_js(self, code):
            raise RuntimeError("window destroyed")

    b = _bare_bridge()
    b._main_window = _Dead()
    thread = threading.Thread(target=b._dispatch_loop, daemon=True)
    thread.start()
    try:
        b._put_event(("status", "after teardown", None))
        time.sleep(0.3)
        assert thread.is_alive()
    finally:
        b._dispatch_stop.set()
        thread.join(timeout=3.0)
    assert [m["ev"][1] for m in _drain(b._events)] == ["after teardown"]


def test_obs_line_is_staged_by_the_caller_and_written_by_the_dispatcher(tmp_path, monkeypatch):
    """The OBS file write is a syscall per caption token; it used to run on the
    receive thread too. _obs_write now only stages the payload."""
    import app.webui as webui

    obs = tmp_path / "obs.txt"
    monkeypatch.setattr(webui, "OBS_FILE", str(obs))
    b = _bare_bridge()
    b.cfg = {"obs_subtitle_enabled": True}
    b._show_badge = lambda: False

    b._obs_write("merhaba")
    assert not obs.exists(), "_obs_write must not touch the filesystem itself"

    b._flush_obs()
    assert obs.read_text(encoding="utf-8") == "merhaba"

    # Unchanged content must not rewrite the file (OBS re-reads on mtime).
    b._obs_write("merhaba")
    before = obs.stat().st_mtime_ns
    b._flush_obs()
    assert obs.stat().st_mtime_ns == before


def test_obs_write_is_a_noop_when_disabled(tmp_path, monkeypatch):
    import app.webui as webui

    obs = tmp_path / "obs.txt"
    monkeypatch.setattr(webui, "OBS_FILE", str(obs))
    b = _bare_bridge()
    b.cfg = {"obs_subtitle_enabled": False}

    b._obs_write("merhaba")
    b._flush_obs()
    assert not obs.exists()


def test_queue_overflow_drops_the_oldest_and_never_raises():
    b = _bare_bridge()
    for i in range(500):                     # maxsize is 400
        b._put_event(("trans", str(i), False, None, 0.0))
    msgs = _drain(b._events)
    assert len(msgs) == 400
    assert msgs[-1]["ev"][1] == "499", "newest event must survive"
