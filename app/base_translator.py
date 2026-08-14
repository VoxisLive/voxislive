"""Shared session machine for every realtime translation engine.

Both engines — Gemini Live (SDK) and Qwen3.5-LiveTranslate (raw websockets) —
run the SAME field-hardened lifecycle: a bounded drop-oldest input queue,
carryover across a planned rotation, backoff-bounded reconnect with
transient/terminal classification, a covert-immediate-close guard, and two
watchdogs (stall on sent-audio-with-no-server-events, and no-output-despite-
input). That machinery lived copy-pasted in multiple files and drifted (see
the 2026-07-04 audit P0 #6); it now lives here once.

Subclass contract — a concrete engine supplies only its protocol:
  * class attrs: HARD_ROTATE_SECONDS, IN_BYTES_PER_SEC (usage divisor),
    TERMINAL_PHRASES, READY_ON_CONNECT (True = _ready fires the moment the
    connection opens, as Gemini/Qwen do; False = the receiver sets it on a
    server 'session live' event instead, for an engine whose protocol
    requires waiting for one).
  * async _connect(self) -> raw connection (websocket engines only; the base
    wraps it in a close-on-exit context manager). Gemini overrides _session_cm
    instead, since its connection IS an async context manager (the SDK).
  * async _open_session(self, conn): send any post-connect config (websocket
    session.update). No-op for Gemini (config is bundled into connect()).
  * async _sender_frame(self, conn, item): send ONE input frame, then call
    self._account_sent(len(item)) for usage/stall accounting.
  * async _receive_loop(self, conn): parse the server event stream, calling the
    shared helpers _reset_stall / _mark_input / _mark_output, self.on_audio /
    self.on_text, self._record_usage("out_sec", …), and raising _Rotate on a
    GoAway. Gemini-only resume-handle capture lives here too.
  * optional hooks: _reset_session_state (reset per-connection parse state),
    _reset_reconnect_state (drop state that must not survive a failed reconnect,
    e.g. Gemini's stale resume handle), _apply_fallback_credentials (swap this
    engine's connection credentials onto a server-provided backup pool — see
    the `fallback` constructor kwarg below; no-op by default).

The behavior constants below are the pre-consolidation values; each engine keeps
its own via class attrs. They are NOT tuning knobs to revisit here.
"""
import asyncio
import contextlib
import logging
import random
import threading
import time
import traceback

from .i18n import t

_log = logging.getLogger("voxis")


class _Rotate(Exception):
    """Signals a planned reconnect ahead of the session ceiling (or a watchdog
    trip / GoAway). Never treated as a transient error.

    heal=True marks a SELF-HEAL rotation (a watchdog trip: stall, or input with
    no output). The reconnect must then start a FRESH session — see
    _run_session — because the reason we are reconnecting is that the CURRENT
    session stopped producing output. Resuming it (Gemini's session_resumption
    handle) carries the stuck state straight back, so the self-heal never heals:
    that is the Qwen->Gemini "translation stops and never resumes until you
    toggle the engine" report (Gemini can latch into silent false-suppression;
    only a truly fresh session escapes it). A planned ceiling rotation or a
    server GoAway is heal=False — resuming there is seamless and correct."""

    def __init__(self, heal: bool = False):
        super().__init__()
        self.heal = heal


class _WatchdogExhausted(Exception):
    """Raised by the sender when the no-output self-heal budget
    (WATCHDOG_ROTATE_MAX) is spent and translated output is still absent.

    Before this existed, an exhausted budget just stopped rotating: the
    session sat "connected" but silently dead until the user noticed and
    restarted by hand (VX-JQGPW5, 2026-08-14 — hi target, Qwen). Propagating
    this to _main() routes it through the same give-up/on_fatal path as a
    terminal engine error, so a paid session gets the Gemini failover and an
    in-taste free session gets a shot at the cascade rescue, instead of
    hanging."""


# HTTP-style status codes that mean "retrying with the same key cannot succeed".
# 429 is deliberately absent: a bare rate-limit is transient and recovers with
# backoff (genuine quota exhaustion is caught by the per-engine phrase markers).
_DEFAULT_TERMINAL_CODES = frozenset({401, 403, 404})


def is_terminal_error(exc, phrases, codes=_DEFAULT_TERMINAL_CODES) -> bool:
    """True when `exc` is a non-retryable auth/permission/quota/4xx failure.

    Prefers a STRUCTURED status code (google.genai APIError.code, a status_code
    attr, …) over substring sniffing, because free-form error text routinely
    embeds unrelated numbers (byte counts, ports, request ids) that would be
    misread as a status code. The phrase markers are specific enough to match the
    message text directly."""
    for attr in ("code", "status_code"):
        val = getattr(exc, attr, None)
        if callable(val):
            try:
                val = val()
            except Exception:
                val = None
        try:
            # val's real type is whatever the exception happens to carry under
            # this attribute name (str/int/callable-result/anything) — genuinely
            # dynamic introspection, guarded by the except below.
            if val is not None and int(val) in codes:  # pyright: ignore[reportArgumentType]
                return True
        except (TypeError, ValueError):
            pass
    text = str(exc).lower()
    return any(p in text for p in phrases)


class BaseTranslator(threading.Thread):
    # --- behavior constants (overridable per engine) ------------------------
    # Bounded input buffer: 50 frames * 32 ms ≈ 1.6 s. On overflow the OLDEST
    # frame is dropped so the session keeps translating the freshest audio.
    QUEUE_MAX = 50
    # After signalling rotation, let the receiver finish the in-flight model_turn
    # so the tail of the previous translation plays out rather than truncated.
    ROTATE_DRAIN_SECONDS = 1.5
    # Cap consecutive transient failures so a hard outage surfaces one actionable
    # status instead of spinning forever.
    MAX_TRANSIENT_FAILURES: int = 8
    # A session the server accepts then closes under this many seconds (no error,
    # no planned rotation) is a covert transient failure — otherwise an
    # account/region/endpoint reject would spin a no-backoff reconnect loop.
    MIN_SESSION_SECONDS = 5.0
    # Stall watchdog: this many SECONDS OF SENT AUDIO with zero server events
    # means the socket is silently dead (TCP black hole after sleep/resume) — a
    # planned rotation is forced. Measured in sent-audio seconds, never wall
    # clock, so quiet periods can never trip it.
    STALL_ROTATE_SECONDS = 20.0
    # No-output watchdog: input transcription arriving but NO output (audio or
    # output transcription) for this long surfaces one actionable status. Gated
    # on RECENT input so a genuine quiet stretch can never trip it.
    NO_OUTPUT_WARN_SECONDS = 12.0
    INPUT_RECENT_SECONDS = 4.0
    # Self-heal escalation: once input-with-no-output has persisted this long,
    # the warning alone is not enough (the Beta-off→Gemini "translation stops"
    # report left the session dead until the user toggled engines by hand) —
    # force a reconnect. Bounded per session by WATCHDOG_ROTATE_MAX so a
    # genuinely output-less account can't spin an endless reconnect loop; the
    # budget refills the moment healthy output resumes. Once the budget is
    # spent and the stream is STILL silent, _sender raises _WatchdogExhausted
    # instead of continuing to sit connected-but-dead (VX-JQGPW5) — _main
    # routes that through _give_up/on_fatal exactly like a terminal error, so
    # a paid session gets the Gemini failover and an in-taste free session
    # gets a shot at the cascade rescue.
    NO_OUTPUT_ROTATE_SECONDS = 22.0
    WATCHDOG_ROTATE_MAX = 3
    # Voice watchdog: translated TEXT is flowing but NO translated AUDIO for this
    # long — the user sees subtitles with no voice (a text-only engine tier, or a
    # broken audio leg). Distinct from NO_OUTPUT above, which needs BOTH absent.
    NO_AUDIO_WARN_SECONDS = 8.0
    # Hard rotation deadline (per engine's session ceiling) and the usage
    # accounting divisor (bytes/sec of the engine's INPUT sample rate).
    HARD_ROTATE_SECONDS = 14.5 * 60
    IN_BYTES_PER_SEC = 32000  # 16 kHz PCM16
    # Terminal-failure classification.
    TERMINAL_CODES = _DEFAULT_TERMINAL_CODES
    TERMINAL_PHRASES = ()
    # When _ready fires: True = on connect (Gemini/Qwen), False = the receiver
    # sets it on a server 'session live' event instead.
    READY_ON_CONNECT = True
    # False for text-only engines (cascade cloud leg): no cloud audio ever
    # arrives, so "text flowing but no audio" is their normal state, not a
    # broken audio leg.
    VOICE_WATCHDOG = True

    # Lazily-bound usage sink (translator._add_usage). Kept off the module import
    # so base_translator stays free of google.genai on the websocket cold path.
    _USAGE_ADD = None

    def __init__(self, api_key, target_lang, on_audio, on_text, on_status, *,
                 rotate_minutes, name="translator", on_fatal=None, fallback=None):
        super().__init__(daemon=True, name=name)
        self.api_key = api_key
        self.target_lang = target_lang
        self.on_audio = on_audio
        self.on_text = on_text
        self.on_status = on_status
        # Called (from the translator thread) when this engine has given up for
        # good — a terminal reject, or transient failures past the cap. Lets the
        # owner substitute another engine rather than leave the user with a dead
        # session; nobody listening means the old behaviour, i.e. the session just
        # stops with a status. Fired at most once.
        self.on_fatal = on_fatal
        self._fatal_fired = False
        # Server-provided backup credential for a sibling pool of the SAME
        # engine (e.g. Qwen's other DashScope key/model tier) — see
        # engines.py / session_key.go's qwenFallbackCredentials. A terminal
        # error (this exact pool is dead: capacity ceiling, spent balance) is
        # worth ONE fast retry against a DIFFERENT pool before abandoning the
        # engine entirely for an on_fatal swap to Gemini — better UX (a session
        # that only has ONE pool problem stays on the higher-quality engine)
        # and less load on a possibly fleet-wide-shared rate limit than
        # grinding the generic transient-retry backoff against the same dead
        # pool. None (the default, and every non-Qwen engine) skips this and
        # behaves exactly as before. Used at most once per translator lifetime.
        self._fallback = fallback
        self._used_fallback = False
        self.rotate_seconds = rotate_minutes * 60
        # Both unset only before run() (the thread entry point) creates them;
        # every reader other than the two explicit pre-thread-start guards
        # below (send_pcm16, stop) only runs once the loop is live — including
        # callbacks scheduled onto the loop itself, which by definition cannot
        # run before it exists.
        self._loop: asyncio.AbstractEventLoop = None  # pyright: ignore[reportAttributeAccessIssue]
        self._queue: asyncio.Queue = None  # pyright: ignore[reportAttributeAccessIssue]
        self._stopping = threading.Event()
        self._ready = threading.Event()
        # Frames carried over a rotation: re-injected into the next session so the
        # ~1-2 s of unsent source audio at cutover is not lost.
        self._carryover: list[bytes] = []
        # Stall watchdog accumulator (loop-thread only, no locking): seconds of
        # audio sent since the last server event. Sender adds, receiver zeroes.
        self._sent_since_recv = 0.0
        # No-output watchdog state (loop-thread only): last input/output monotonic
        # timestamps + a once-per-session latch.
        self._last_input_ts = 0.0
        self._last_output_ts = 0.0
        self._no_output_warned = False
        # Self-heal reconnect budget (per translator lifetime, NOT reset by
        # _reset_watchdogs on each reconnect — that would defeat the loop guard).
        # Refilled to 0 in the sender when fresh output is observed.
        self._watchdog_rotations = 0
        # Voice watchdog state: audio vs text output tracked separately so
        # "captions flowing, no voice" is distinguishable from "no output at all".
        self._last_audio_ts = 0.0
        self._last_text_ts = 0.0
        self._no_audio_warned = False
        # When the current session became live (None until ready), so the
        # error/exit paths can tell a connect failure from a dropped session.
        self._session_started: float | None = None
        # Reconnect backoff + last-printed error, promoted to fields so a healthy
        # reconnect (inside _run_session) can reset them.
        self._backoff = 1.0
        self._last_error_text = None

    # --- public contract (identical across engines) -------------------------
    def send_pcm16(self, data: bytes):
        if self._loop and self._queue and not self._stopping.is_set():
            try:
                self._loop.call_soon_threadsafe(self._put_nowait, data)
            except RuntimeError:
                # The loop is shutting down — drop the frame.
                pass

    def _put_nowait(self, item):
        try:
            self._queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass
        # Backpressure: drop the OLDEST frame to keep the freshest audio. Runs on
        # the loop thread with no await, so it is atomic vs the single sender
        # consumer. Count the loss so sustained drops are visible in telemetry.
        try:
            self._queue.get_nowait()
            self._record_usage("dropped_frames", 1)
        except asyncio.QueueEmpty:
            pass
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    def stop(self):
        self._stopping.set()
        # Nudge the loop so a stop lands promptly even mid-backoff / mid-connect
        # (guarded for an already-closed loop).
        if self._loop:
            try:
                self._loop.call_soon_threadsafe(lambda: None)
            except RuntimeError:
                pass

    def _on_thread_exit(self) -> None:
        """Engine hook fired once as the translator thread unwinds. Default is a
        no-op; an engine uses it to report per-session accounting whose LAST
        session would otherwise never be judged (rotation-time hooks only ever
        see the sessions before the final one)."""

    def wait_ready(self, timeout: float = 15) -> bool:
        return self._ready.wait(timeout)

    # --- usage / watchdog helpers (shared) ----------------------------------
    def _record_usage(self, key: str, amount: float):
        add = BaseTranslator._USAGE_ADD
        if add is None:
            from .translator import _add_usage  # lazy: keep vendor runtimes off cold start
            # staticmethod() so a class-level lookup never tries to bind `self`
            # (BaseTranslator._USAGE_ADD is read via the class, not an instance).
            BaseTranslator._USAGE_ADD = staticmethod(_add_usage)
            add = _add_usage
        add(key, amount)

    def _account_sent(self, nbytes: int):
        secs = nbytes / self.IN_BYTES_PER_SEC
        self._record_usage("in_sec", secs)
        self._sent_since_recv += secs

    def _reset_stall(self):
        # Any server event proves the connection is alive.
        self._sent_since_recv = 0.0

    def _mark_input(self):
        self._last_input_ts = time.monotonic()

    def _mark_output(self):
        self._last_output_ts = time.monotonic()

    def _mark_audio_output(self):
        """Translated AUDIO frame delivered to the sink. Also counts as generic
        output (keeps the no-output watchdog satisfied)."""
        now = time.monotonic()
        self._last_audio_ts = now
        self._last_output_ts = now

    def _mark_text_output(self):
        """Translated TEXT (caption) delivered. Generic output too — but tracked
        apart from audio so the voice watchdog can spot text-without-voice."""
        now = time.monotonic()
        self._last_text_ts = now
        self._last_output_ts = now

    def _reset_watchdogs(self):
        self._sent_since_recv = 0.0
        self._last_input_ts = 0.0
        self._last_output_ts = 0.0
        self._no_output_warned = False
        self._last_audio_ts = 0.0
        self._last_text_ts = 0.0
        self._no_audio_warned = False

    # --- subclass hooks (defaults) ------------------------------------------
    def _session_cm(self):
        """Connection lifecycle as an async context manager. Default = websocket
        style: dial via _connect(), close on exit. Gemini overrides with the SDK's
        own async context manager."""
        return self._ws_session_cm()

    @contextlib.asynccontextmanager
    async def _ws_session_cm(self):
        ws = await self._connect()
        try:
            yield ws
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    async def _connect(self):
        raise NotImplementedError

    async def _open_session(self, conn):
        """Post-connect session config. No-op for engines that bundle config into
        connect (Gemini)."""
        return None

    async def _sender_frame(self, conn, item):
        raise NotImplementedError

    async def _receive_loop(self, conn):
        raise NotImplementedError

    def _reset_session_state(self):
        """Reset per-connection parse state (e.g. cumulative-caption accumulators)
        on each new session. Base: nothing."""
        return None

    def _apply_fallback_credentials(self):
        """Swap this engine's connection credentials onto self._fallback (called
        once, immediately before the next reconnect — see _main's terminal-error
        branch). Base: nothing, since only engines with a multi-pool concept
        (Qwen) accept a `fallback` in the first place."""
        return None

    def _reset_reconnect_state(self):
        """Drop connection-scoped state that must not survive a FAILED reconnect
        (e.g. Gemini's stale resume handle). Base: nothing."""
        return None

    def _is_terminal(self, exc) -> bool:
        return is_terminal_error(exc, self.TERMINAL_PHRASES, self.TERMINAL_CODES)

    def _give_up(self, exc) -> None:
        """This engine is finished for this session. Offer the owner a chance to
        substitute a different one before the user is shown a dead session.

        Every path that abandons the reconnect loop routes through here, so a
        replacement engine is reachable from a terminal reject (a spent DashScope
        balance reports as 'arrearage'/'quota'), from exhausted transient retries,
        and from the covert immediate-close. If on_fatal returns truthy it has
        taken over and the failure stays silent; otherwise the status surfaces as
        it always did."""
        _log.error("%s: abandoning the reconnect loop: %r", self.name, exc)
        if self.on_fatal is not None and not self._fatal_fired:
            self._fatal_fired = True
            try:
                if self.on_fatal(exc):
                    _log.info("%s: a substitute engine took over", self.name)
                    return
            except Exception:  # a broken handler must not mask the real failure
                traceback.print_exc()
        # Generic, not st_conn_err: no substitute engine took over, so this is
        # not a retry (the "retrying in 0s" phrasing was misleading) and the
        # raw exc — which can be an upstream provider's verbatim error text,
        # e.g. DashScope's {"code":"COMMON_ERROR","message":"thread pool
        # exhausted..."} — must not reach the user unfiltered. Full exc still
        # goes to the log line above for field diagnosis.
        self.on_status(t("st_engine_gone", name=self.name))
        traceback.print_exc()

    # --- thread body --------------------------------------------------------
    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue(maxsize=self.QUEUE_MAX)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            # The translator thread must not die silently — surface the error.
            if not self._stopping.is_set():
                self.on_status(t("st_conn_err", name=self.name, s=0, e=e))
                traceback.print_exc()
        finally:
            self._stopping.set()
            # Last chance for an engine to report what its final session left
            # behind — after this the thread is gone. Best-effort by contract:
            # a broken hook must not take the teardown with it.
            try:
                self._on_thread_exit()
            except Exception:
                traceback.print_exc()
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            self._loop.close()

    async def _main(self):
        self._backoff = 1.0
        self._last_error_text = None
        transient_failures = 0
        while not self._stopping.is_set():
            # _ready (waited on by wait_ready) must mean "a session is currently
            # live": clear on every iteration so the reconnect/rotation gap is
            # never reported ready.
            self._ready.clear()
            self._session_started = None
            try:
                rotating = await self._run_session()
                started = self._session_started
                # A planned rotation, or a session that stayed alive past the
                # minimum lifetime AND actually produced output, is a healthy end:
                # clear the transient machinery and reconnect cleanly. A session the
                # server accepted then closed almost immediately (no error, no
                # rotation) — or held open but produced nothing — is a covert
                # failure and must count toward MAX_TRANSIENT_FAILURES like any
                # other transient drop; time-alive alone is not proof of health.
                if rotating or (started is not None
                                and time.monotonic() - started >= self.MIN_SESSION_SECONDS
                                and self._last_output_ts > 0.0):
                    transient_failures = 0
                    if not self._stopping.is_set():
                        _log.info("%s: session renewing (planned rotation)", self.name)
                        self.on_status(t("st_renewing", name=self.name))
                elif not self._stopping.is_set():
                    self._reset_reconnect_state()
                    transient_failures += 1
                    _log.warning("%s: server closed the session immediately "
                                 "(failure %d/%d, backoff %.1fs)", self.name,
                                 transient_failures, self.MAX_TRANSIENT_FAILURES,
                                 self._backoff)
                    if transient_failures >= self.MAX_TRANSIENT_FAILURES:
                        self._give_up(t("st_server_closed"))
                        break
                    self.on_status(t("st_conn_err", name=self.name, s=self._backoff,
                                     e=t("st_server_closed")))
                    jitter = random.uniform(0.85, 1.15)
                    await asyncio.sleep(self._backoff * jitter)
                    self._backoff = min(self._backoff * 1.6, 6)
            except _Rotate:
                # Defensive: a _Rotate must not be treated as a transient error.
                self._ready.clear()
                continue
            except (asyncio.CancelledError, GeneratorExit):
                raise
            except Exception as e:
                self._ready.clear()
                if self._stopping.is_set():
                    break
                # No-output watchdog exhausted its self-heal budget: this is not
                # a fresh failure to classify/retry, it's the same dead stream
                # we already tried (and failed) to reconnect out of 3 times.
                # Give up immediately, same as a terminal error, instead of
                # feeding it through backoff/transient-failure counting.
                if isinstance(e, _WatchdogExhausted):
                    _log.error("%s: no-output watchdog exhausted, giving up: %r",
                               self.name, e)
                    self._give_up(e)
                    break
                # Terminal (auth/permission/quota/4xx): retrying with the same key
                # cannot succeed — give up and let a substitute engine step in.
                # EXCEPT: an unused server-provided fallback pool (see __init__)
                # is worth one fast, immediate retry first — it's a DIFFERENT
                # credential, so "cannot succeed" doesn't apply to it, and a
                # session that only lost ONE pool stays on the better engine
                # instead of an on_fatal swap to Gemini.
                if self._is_terminal(e):
                    if self._fallback and not self._used_fallback:
                        self._used_fallback = True
                        self._apply_fallback_credentials()
                        self._reset_reconnect_state()
                        _log.warning("%s: terminal error on primary pool (%r) — "
                                     "retrying once via the fallback pool before "
                                     "giving up", self.name, e)
                        self.on_status(t("st_renewing", name=self.name))
                        continue
                    _log.error("%s: terminal error, not retrying: %r", self.name, e)
                    self._give_up(e)
                    break
                # A session that ran past the minimum lifetime AND actually produced
                # output proves the path works; a later drop starts a fresh failure
                # streak. Time-alive alone is not enough — a server that accepts the
                # connection, holds it open past MIN_SESSION_SECONDS, then drops it
                # having produced nothing (DashScope's "thread pool exhausted", seen
                # 2026-08-01) kept resetting this counter every retry, so it never
                # reached MAX_TRANSIENT_FAILURES and _give_up()/on_fatal never fired
                # — the engine never failed over even though it was fully dead.
                started = self._session_started
                if (started is not None and time.monotonic() - started >= self.MIN_SESSION_SECONDS
                        and self._last_output_ts > 0.0):
                    transient_failures = 0
                transient_failures += 1
                self._reset_reconnect_state()
                _log.warning("%s: transient error (failure %d/%d, retry in %.1fs): %r",
                             self.name, transient_failures,
                             self.MAX_TRANSIENT_FAILURES, self._backoff, e)
                if transient_failures >= self.MAX_TRANSIENT_FAILURES:
                    _log.error("%s: transient retries exhausted — giving up", self.name)
                    self._give_up(e)
                    break
                self.on_status(t("st_conn_err", name=self.name, s=int(self._backoff), e=e))
                # Suppress repeated identical tracebacks: a flapping link would
                # otherwise flood stderr with the same stack on every retry.
                err_text = repr(e)
                if err_text != self._last_error_text:
                    traceback.print_exc()
                    self._last_error_text = err_text
                jitter = random.uniform(0.85, 1.15)
                await asyncio.sleep(self._backoff * jitter)
                # Cap reconnect backoff at 6 s to recover quickly from drops.
                self._backoff = min(self._backoff * 1.6, 6)

    async def _run_session(self) -> bool:
        """One connect→serve→teardown cycle. Returns True if the session ended on
        a planned rotation (vs a plain close). Raises on a real error so _main can
        classify it terminal/transient."""
        async with self._session_cm() as conn:
            # Config send + carryover reinjection both complete before the sender
            # task starts, so their order is immaterial; do config first to mirror
            # the websocket engines (Gemini's _open_session is a no-op).
            await self._open_session(conn)
            self._reinject_carryover()
            _log.info("%s: session connected (target=%s, model=%s)",
                      self.name, self.target_lang, getattr(self, "model", "?"))
            self.on_status(t("st_connected", name=self.name, lang=self.target_lang))
            if self.READY_ON_CONNECT:
                self._ready.set()
            # A live connection proves the path works: reset backoff so a later
            # drop starts fresh, and clear the dedup so its first error prints.
            self._backoff = 1.0
            self._last_error_text = None
            self._reset_watchdogs()
            self._reset_session_state()
            self._session_started = time.monotonic()
            started = self._session_started
            sender = asyncio.create_task(self._sender(conn, started))
            receiver = asyncio.create_task(self._receive_loop(conn))
            done, pending = await asyncio.wait(
                {sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            rotating = heal = False
            for tsk in done:
                if tsk.cancelled():
                    continue
                exc = tsk.exception()
                if isinstance(exc, _Rotate):
                    rotating = True
                    heal = heal or exc.heal
            if rotating and not self._stopping.is_set():
                # Overlap-and-drain: keep the old receiver alive briefly so the
                # in-flight model_turn plays out, THEN snapshot the unsent queue so
                # frames arriving during the grace window keep arrival order.
                await self._drain_receiver(receiver)
                self._snapshot_carryover()
            # Session is no longer live — stop reporting ready before teardown.
            self._ready.clear()
            for tsk in pending:
                tsk.cancel()
            for tsk in done:
                if tsk.cancelled():
                    continue
                exc = tsk.exception()
                if exc and not isinstance(exc, _Rotate):
                    raise exc
        # A self-heal rotation reconnects because the session went output-dead;
        # drop any resume handle (done AFTER drain captured the tail) so the next
        # connect is a genuinely fresh session instead of resuming the stuck one.
        if heal:
            self._reset_reconnect_state()
        return rotating

    # --- carryover (shared) -------------------------------------------------
    def _snapshot_carryover(self):
        """Move every unsent queued frame into the carryover buffer (loop thread,
        no await — atomic vs the single sender). Bounded by QUEUE_MAX."""
        self._carryover = []
        while True:
            try:
                self._carryover.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

    def _reinject_carryover(self):
        """Push carried-over frames into the fresh session's queue, oldest first,
        so the rotation tail is sent before any new audio."""
        if not self._carryover:
            return
        for frame in self._carryover:
            self._put_nowait(frame)
        self._carryover = []

    async def _drain_receiver(self, receiver: asyncio.Task):
        """Give the old session's receiver a brief grace period to emit the tail
        of the in-flight model_turn before the session is torn down."""
        try:
            await asyncio.wait_for(asyncio.shield(receiver),
                                   timeout=self.ROTATE_DRAIN_SECONDS)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            # A receiver error during drain is non-fatal: we are rotating anyway.
            pass

    # --- sender loop (shared; frame send delegated to _sender_frame) --------
    async def _sender(self, conn, started: float):
        while not self._stopping.is_set():
            # Rotation is checked every iteration, independent of the quiet window,
            # so a steady-state stream still rotates on schedule. The hard deadline
            # forces a cutover even mid-speech before the server ceiling.
            elapsed = time.monotonic() - started
            if elapsed > self.rotate_seconds or elapsed > self.HARD_ROTATE_SECONDS:
                raise _Rotate()
            # Stall watchdog: sent audio piling up with zero server events means a
            # silently dead socket — rotate instead of streaming into a black hole
            # (a hung TCP connection may never raise in the receiver).
            if self._sent_since_recv >= self.STALL_ROTATE_SECONDS:
                self._sent_since_recv = 0.0
                _log.warning("%s: stall watchdog — %.0fs of audio sent with no "
                             "server event, forcing a fresh session", self.name,
                             self.STALL_ROTATE_SECONDS)
                self.on_status(t("st_stall_reconnect", name=self.name,
                                 s=int(self.STALL_ROTATE_SECONDS)))
                raise _Rotate(heal=True)
            # No-output watchdog: input transcription recently but no output.
            # Warn once, then SELF-HEAL — force a reconnect if the stall persists,
            # instead of streaming into a black hole until the user toggles the
            # engine by hand (the Beta-off→Gemini "translation stops" report).
            now = time.monotonic()
            if (self._last_input_ts > 0.0
                    and now - self._last_input_ts <= self.INPUT_RECENT_SECONDS):
                last_out = self._last_output_ts if self._last_output_ts > 0.0 else started
                stalled = now - last_out
                if stalled < self.NO_OUTPUT_WARN_SECONDS:
                    self._watchdog_rotations = 0  # output is fresh — refill budget
                elif not self._no_output_warned:
                    self._no_output_warned = True
                    self.on_status(t("st_no_output_warning"))
                if stalled >= self.NO_OUTPUT_ROTATE_SECONDS:
                    if self._watchdog_rotations < self.WATCHDOG_ROTATE_MAX:
                        self._watchdog_rotations += 1
                        _log.warning("%s: no-output watchdog — input %.0fs ago but no "
                                     "translation for %.0fs, self-heal rotation %d/%d",
                                     self.name, now - self._last_input_ts, stalled,
                                     self._watchdog_rotations, self.WATCHDOG_ROTATE_MAX)
                        self.on_status(t("st_noout_reconnect", name=self.name,
                                         s=int(self.NO_OUTPUT_ROTATE_SECONDS)))
                        raise _Rotate(heal=True)
                    # Self-heal budget spent and the stream is still silent — a
                    # fresh reconnect would just repeat what already failed 3
                    # times. Escalate to give-up instead of looping in place.
                    raise _WatchdogExhausted(
                        f"no output {stalled:.0f}s after last input, "
                        f"{self._watchdog_rotations}/{self.WATCHDOG_ROTATE_MAX} "
                        "self-heal rotations exhausted")
            # Voice watchdog: translated TEXT is flowing (recently) but translated
            # AUDIO is absent — subtitles with no voice. Gated on recent text so a
            # normal end-of-speech (audio + text stop together) never trips it, and
            # on a minimum session age so the first utterance's lag doesn't.
            if (self.VOICE_WATCHDOG
                    and self._last_text_ts > 0.0 and not self._no_audio_warned
                    and now - self._last_text_ts <= self.INPUT_RECENT_SECONDS
                    and now - started >= self.NO_AUDIO_WARN_SECONDS):
                if (self._last_audio_ts == 0.0
                        or now - self._last_audio_ts >= self.NO_AUDIO_WARN_SECONDS):
                    self._no_audio_warned = True
                    self.on_status(t("st_no_voice_warning"))
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                # Quiet window — loop back and re-check the rotation deadline.
                continue
            if not item:
                continue
            await self._sender_frame(conn, item)
