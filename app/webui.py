"""pywebview bridge between the web UI and the Python audio engine.

JavaScript invokes Bridge methods through `window.pywebview.api`; the UI polls
`poll()` to drain status, translation and telemetry events — every 70 ms while
a session is live (the caption is the fastest user-visible signal, so the poll
cadence is part of the latency budget), relaxing to 250 ms when idle.
"""
import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable

import webview

from . import APP_VERSION, i18n, store_review, sysaudio, transcript_store
from .audio_io import (
    Capture,
    detect_virtual_cable,
    find_device,
    list_device_names,
    play_test_tone,
)
from .config import (
    DEFAULT_TERMS,
    ENGINE_CASCADE,
    GEMINI_VOICES,
    IS_OFFICIAL_RELEASE,
    LANGS,
    QUALITY_PRESETS,
    apply_profile,
    parse_hotwords,
    save_config,
)
from .history_bridge import HistoryMixin, _near_duplicate, _strip_inline_repeat
from .i18n import t
from .paths import icon_path, user_path, web_dir
from .pipeline import ModeController

WEB_DIR = web_dir()
OBS_FILE = user_path("obs_subtitle.txt")

# LANGS moved to config.py (SSOT, also read by scripts/gen_app_manifest.py);
# imported above and re-exported here so existing `webui.LANGS` callers/tests
# are unaffected.
def _parse_semver(v):
    """"1.0.54" -> (1, 0, 54); None on anything malformed. Never raises —
    a version string from a remote manifest must not be able to crash the
    update-available check."""
    try:
        return tuple(int(p) for p in (v or "").strip().split("."))
    except (ValueError, AttributeError):
        return None


def _free_voiced_langs():
    """Targets the free tier can SPEAK (the rest fall back to captions-only).

    Reads the voice registry, not sherpa — importing local_tts costs nothing
    here and keeps one source of truth, so adding a voice to VOICES lights it
    up in the picker with no second list to update."""
    try:
        from . import local_tts
        return [lang for lang in LANGS if local_tts.voice_available(lang)]
    except Exception:  # a broken registry must not take the whole UI down
        _log.exception("voiced-language list unavailable")
        return []


def _voice_choice_langs(cfg):
    """Targets whose translated voice can be gendered (see config.VOICE_BY_GENDER).

    Mirrors _free_voiced_langs' shape so the UI treats both the same way: a list
    of picker codes, empty on any failure — a broken list must dim a hint, never
    take the window down."""
    try:
        from .config import qwen_can_voice
        return [lang for lang in LANGS if qwen_can_voice(cfg, lang)]
    except Exception:
        _log.exception("voice-choice language list unavailable")
        return []


LINE_GAP = 2.5
# When a speaker change has been detected, the translated stream is split at
# the next micro-pause this long — far below LINE_GAP, so back-to-back
# speakers still land in separate, separately-labeled turns.
SPK_GAP = 0.7
# The model's simultaneous-interpretation "ear-voice span": how far behind the
# source the translated output trails (see CLAUDE.md "Translation Latency" —
# not client-tunable, documented as "a few seconds"; bench p50 ~4.0s). Used
# to bound _pop_source's claim: a translation turn that just finished at time
# `now` was produced from source heard up to roughly `now - SRC_LAG_S`, NOT
# source heard by `now` itself. A CONTINUOUSLY-narrated source stream (no
# genuine pause — Qwen's ASR) never gives its own boundary signal, so the
# only usable cutoff is this lag-adjusted "now", not the turn's own start
# time: a turn's start-to-finish span varies with how much it had to say,
# while the model's lag behind the mic does not, so start-time is not a
# reliable proxy for "how far the source has actually progressed". Kept
# slightly below the documented average on purpose: under-claiming just
# leaves a turn without its own caption (caught by a later turn instead);
# over-claiming mispairs content into the wrong turn, which is the bug this
# exists to prevent.
SRC_LAG_S = 3.0
FADE_MS = 6.0
# Turn-length safety valves for engines that never pause long enough to trip
# LINE_GAP. Past MAX_LINE_CHARS (or MAX_LINE_SECONDS in one turn) the stream is
# split at the NEXT sentence end, so the break lands on a real boundary rather
# than mid-clause; HARD_LINE_CHARS splits regardless, for a run-on that never
# punctuates. Chosen so a normal utterance (~88 chars in a measured session) is
# never split and only the pathological ones are.
MAX_LINE_CHARS = 180
MAX_LINE_SECONDS = 12.0
HARD_LINE_CHARS = 400
SENTENCE_END = (".", "!", "?", "…", "。", "！", "？")
# Meeting-terms box. The engine keeps the first 50 pairs (a DashScope limit);
# the character cap is just a sane bound on what gets written to config.json.
HOTWORDS_MAX_CHARS = 4000
HOTWORDS_MAX_TERMS = 50
# Prefetched session-key freshness window (seconds). Short on purpose so a
# stale entry falls back to the normal synchronous fetch. Only RAW keys are
# ever cached — a single-use ephemeral token (2-min new-session window,
# shorter than this TTL) would fail the first connect terminally, so
# _prefetch_session_key skips caching those.
KEY_PREFETCH_TTL = 240.0
# Overlay/OBS subtitle width cap on a word boundary so a runaway turn never
# produces an unbounded single line in the overlay window or the OBS file.
SUBTITLE_MAX = 260
# Watchdog: abandon a hotkey capture that receives no keypress within this many
# seconds so the blocking read can never hang the bridge thread.
HOTKEY_CAPTURE_TIMEOUT = 8.0

_log = logging.getLogger("voxis.webui")

# Locale-independent default-device sentinel. set_device treats an empty string
# as "system default" for both input and output; the UI renders
# t('default_mic') but always round-trips this sentinel so device matching never
# depends on the active UI language.
DEFAULT_DEVICE = ""


def _cap_subtitle(text: str, limit: int = SUBTITLE_MAX) -> str:
    """Trim a caption to the most recent `limit` chars on a word boundary so the
    leading partial word is dropped rather than shown mid-token."""
    if len(text) <= limit:
        return text
    cut = text[-limit:]
    sp = cut.find(" ")
    return cut[sp + 1:] if 0 <= sp < 40 else cut


class _LegState:
    """Per-direction transcript accumulators.

    A meeting runs TWO translators — incoming (other party -> user) and outgoing
    (user -> other party) — and both used to stream into one set of buffers, so
    the two translations interleaved inside a single caption line and landed in
    the record indistinguishable from each other. The lock around _on_text kept
    that from corrupting the buffers, but it could not keep the two
    CONVERSATIONS apart. Each leg now accumulates on its own; the turn list they
    both append to stays shared, because the record is one chronological
    timeline (turns carry `leg` to say which side spoke).

    Video/Game mode only ever uses the incoming leg."""

    __slots__ = (
        "cur_line",
        "last_src_t",
        "last_t",
        "pending_spk_break",
        "src_buf",
        "src_done",
        "src_marks",
        "src_spk",
        "turn_start",
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.cur_line = ""
        self.last_t = 0.0
        self.turn_start = 0.0
        # See Bridge.__init__ for why the completed-source queue is a FIFO and
        # what the marks are for.
        self.src_buf = ""
        self.src_done: list[tuple[int | None, str, float]] = []
        self.src_marks: list[tuple[float, int]] = []
        self.last_src_t = 0.0
        self.src_spk: int | None = None
        self.pending_spk_break = False


def _autofill_meeting_devices(cfg):
    """Auto-select an installed virtual cable for the two-way meeting path so the
    user never has to hand-edit config.json. Only fills a field that is unset or
    no longer resolves to a present device — a deliberate, valid choice is kept.

    `system_capture` (the vbcable-backend incoming capture device, pipeline.py
    `_acquire_capture`) is the same physical endpoint as `meeting_virtual_mic`
    (both are the cable's recording/output side) and must be kept in sync with
    it — a user whose only virtual cable is VoiceMeeter (not VB-CABLE) would
    otherwise have `meeting_virtual_mic` autofilled correctly while
    `system_capture` stays on the hardcoded VB-CABLE-only default, crashing
    both video mode (feedback guard) and meeting mode (device not found)."""
    devs = cfg.setdefault("devices", {})

    def resolves(name, kind):
        if not name:
            return False
        try:
            find_device(name, kind)
            return True
        except Exception:
            return False

    play_ok = resolves(devs.get("meeting_mic_playback", ""), "output")
    rec_ok = resolves(devs.get("meeting_virtual_mic", ""), "input")
    capture_ok = resolves(devs.get("system_capture", ""), "input")
    if play_ok and rec_ok and capture_ok:
        return
    found = detect_virtual_cable()
    if not found:
        return
    play, rec = found
    if not play_ok:
        devs["meeting_mic_playback"] = play
    if not rec_ok:
        devs["meeting_virtual_mic"] = rec
    if not capture_ok:
        devs["system_capture"] = rec
    save_config(cfg)


class Bridge(HistoryMixin):
    def __init__(self, cfg):
        self.cfg = cfg
        # Set on successful auth; used as the index into the BYOK store.
        self._user_id: str | None = None
        # Last license/quota snapshot from verify; the paid-tier badge gate reads it.
        self._last_quota: dict | None = None
        # One-shot guard for the app_launched funnel milestone (check_auth may run
        # several times per process; the event should fire once).
        self._launch_reported: bool = False
        # One-shot guard for the anonymous app_opened milestone. Distinct from
        # app_launched: this fires on the FIRST check_auth regardless of login,
        # so the funnel can see opens that never reach authentication.
        self._opened_reported: bool = False
        # One-shot guard for the background app.json manifest check (get_init
        # can in principle run more than once per process — a settings restart
        # reloads the page — and this must fire at most once per launch).
        self._manifest_check_started: bool = False
        # The free-voice preview loads a voice (and may download one) off the UI
        # thread; one at a time, so a double click can't race two downloads.
        self._preview_lock = threading.Lock()
        self._preview_busy: bool = False
        # The last line Voxis SPOKE, kept apart from self._lines because stop()
        # clears those once the transcript is saved — and the A/B card is offered
        # precisely AFTER stop, when the user is finally looking at the window.
        # Without this the demo has nothing to replay at the one moment it runs.
        self._last_line: str = ""
        # Resolve "" (= never explicitly chosen) to the Windows display
        # language, and write the resolution back so get_init/JS and the
        # Settings dropdown all see one concrete locale. Not persisted here:
        # until the user picks a language, each launch follows the OS.
        cfg["ui_language"] = i18n.resolve_language(cfg.get("ui_language", ""))
        i18n.set_language(cfg["ui_language"])

        # Bounded like every other queue in the engine: if the webview stops
        # polling (hung/backgrounded window) events must not accumulate without
        # limit. _put_event drops the OLDEST on overflow — the UI shows a live
        # stream, so the freshest events always win.
        self._events: queue.Queue = queue.Queue(maxsize=400)
        # Instant-push channel, drained by _dispatch_loop. Separate from _events
        # so the poll backstop still holds every event even if a push is dropped.
        self._push_q: queue.Queue = queue.Queue(maxsize=400)
        self._event_seq = 0
        self._seq_lock = threading.Lock()
        self._dispatch_stop = threading.Event()
        # Latest OBS subtitle payload, written by the dispatcher thread instead of
        # by the translator's receive thread (see _dispatch_loop). A slot, not a
        # queue: only the newest line matters, and coalescing means fewer mtime
        # changes for OBS to re-read.
        self._obs_pending = None
        self._obs_lock = threading.Lock()
        # The thread itself is started at the very END of __init__ (see below):
        # _dispatch_loop touches _main_window, _last_obs_write and cfg, so it
        # must not race a half-built Bridge.
        # Serialize config writes: pywebview runs each JS api call on its own
        # thread, so a slider drag can overlap several _save_cfg calls. Without
        # this they raced on the on-disk file (see save_config) and one would
        # spuriously fail with a "cannot write to disk" error.
        self._save_lock = threading.Lock()
        self.controller = ModeController(
            cfg, None, self._on_text, self._on_status,
            on_usage_reported=self._on_usage_reported,
            on_quota_exceeded=self._on_quota_exceeded,
            on_session_failed=self._on_session_failed,
            on_speaker=self._on_speaker,
        )

        self._lines = []
        # Per-direction accumulators (see _LegState). Video/Game uses only the
        # incoming leg; a meeting drives both from two translator threads.
        self._legs = {"incoming": _LegState(), "outgoing": _LegState()}
        # Source-transcription stream, paired to translation turns by TIMESTAMP,
        # not by matching pause patterns between the two independent streams.
        # _src_buf accumulates the in-flight source utterance's deltas; a
        # completed utterance (segmented by a >LINE_GAP pause in the source
        # stream, as Gemini produces) is queued in _src_done until a translation
        # turn whose own start-time is >= the utterance's last-heard time pops
        # it. A FIFO — not a single slot — so two source utterances completing
        # before one translation turn finalizes cannot overwrite each other (the
        # old two-slot _last_src/_cur_src scheme dropped the first, and its
        # per-turn _cur_src clear wiped source belonging to a later turn,
        # blanking the JSON `src` field localization/dubbing relies on — Ivo,
        # 1.0.27). Each entry is (speaker, text, last_heard_ts) — see _pop_source.
        # These live on the leg (see _LegState) so a meeting's two directions
        # cannot pair one side's source with the other side's translation.
        # Arrival checkpoints (src_marks) are (timestamp, cumulative length in
        # src_buf): they let _pop_source(cutoff) return only the PREFIX that had
        # arrived by cutoff and leave the rest queued for a later turn.
        #
        # Speaker labeling (local tracker, incoming direction). _cur_spk is the
        # label the tracker believes is talking NOW; _src_spk is the label the
        # in-flight source buffer STARTED under (the buffer finalizes on the
        # next arrival, by which time _cur_spk may already be the next voice).
        # Labels are anonymous session-scoped ints rendered as "S1"/"S2" —
        # deliberately language-neutral, like professional subtitle tags, so
        # exports read the same regardless of UI language.
        self._cur_spk: int | None = None
        self._spk_seen: set[int] = set()
        self._session_file = None
        # Path of the transcript auto-saved by the most recent stop(). Unlike
        # _session_file it SURVIVES the stop-time buffer clear, so a user who
        # presses Stop and then clicks "Save transcript" gets the already-saved
        # file back instead of a confusing "nothing to save".
        self._last_saved_file = None
        # Structured, timestamped turn log for JSON persistence + caption export.
        # Each entry: {"t": offset_s, "dir": "out", "src": str, "text": str}.
        # Parallel to self._lines (kept for the plain-text path); reset per session.
        self._turns = []
        # Engine lifecycle (connect / renew / reconnect / watchdog) as timestamped
        # entries, persisted alongside the turns. Without these a saved transcript
        # cannot answer "did it drop at 16:31?" — the status line scrolled past in
        # the UI and reached no file at all (session audit 2026-07-28).
        self._session_events: list[dict] = []
        # The source (input-transcription) stream with ARRIVAL timestamps, kept
        # independently of how it gets paired onto turns. The per-turn `src`
        # field is a best-effort pairing built from a fixed lag estimate, and on
        # an engine whose source stream trails the translation that estimate is
        # wrong (see the SRC_LAG_S row in CLAUDE.md). Until now the record kept
        # only the RESULT of that pairing, so a bad pairing could not even be
        # measured after the fact, let alone re-derived. This track is the raw
        # material: what arrived, and when.
        self._src_track: list[dict] = []
        # Its counterpart on the OUTPUT side: cumulative seconds of
        # translated speech the engine produced, sampled on the caption
        # clock. Together the two tracks say what was heard, what was
        # shown, and where the two diverge.
        self._audio_track: list[dict] = []
        self._session_start = 0.0
        # Per-session output folder, decided at start so the transcript JSON, its
        # caption exports, and the optional dual-track WAVs all land together in
        # one self-contained directory (Ivo, 1.0.28). _session_dirname is the bare
        # folder name (voxis_<stamp>); _session_dir is its full path under the
        # active transcripts dir. Both cleared on stop.
        self._session_dir = None
        self._session_dirname = None
        self._overlay_win = None
        self._overlay_text = ""
        self._overlay_until = 0.0
        self._maximized = False
        self._minimized = False
        # Latest non-maximized window geometry, persisted to cfg["window"] on close
        # and restored at next launch.
        self._win_geom = {}
        self._badge = (t("badge_idle"), "#8593a6", "")
        # Assigned in run() once the main window exists; referenced by
        # win_* controls before then, so default to None.
        self._main_window: webview.Window | None = None
        # Serializes the session lifecycle: start/stop/_maybe_restart all run on
        # background threads, so without this a rapid start→stop or a flurry of
        # set_cfg restarts could spawn racing _start threads against one
        # controller. _lifecycle holds the lock for the duration of one
        # transition; _restart_token debounces set_cfg-driven restarts.
        self._lifecycle = threading.Lock()
        # Serializes the shared transcript/overlay/OBS buffers that the audio
        # receiver thread(s) mutate via _on_text. Meeting mode runs two such
        # threads, so the read-modify-write must not interleave. RLock because
        # several JS-facing methods (save/clear transcript) take it and can be
        # reached from paths already holding it on the same thread.
        self._text_lock = threading.RLock()
        # The OBS file write and the evaluate_js push both used to happen INSIDE
        # this lock, on the receive thread. Both are now staged for the
        # dispatcher thread, so the lock is held only for in-memory bookkeeping.
        self._save_lock = threading.Lock()
        self._restart_token = 0
        self._last_obs_write = None
        self._hotkey_cancel = False
        # Rolling tail of recent status lines (raw, incl. the "capture: backend=..."
        # diagnostic) + the last coarse error code — assembled into a problem
        # report's diagnostics. Bounded so it can never grow unbounded.
        self._status_log: list[str] = []
        self._last_error_code = ""
        # Per-session failure flag. _last_error_code is sticky across sessions (it
        # rides into problem reports); the rating prompt needs to know whether
        # THIS session failed, so it gets its own flag, reset on every start.
        self._session_error = False
        # Prefetched /auth/session-key result per incoming target (official
        # build): warmed in the background at login / target change / session
        # stop so pressing Start skips the issuance round-trip (~200-400 ms).
        # Single-use + short TTL — on any miss the start does its normal
        # synchronous fetch, so failures cost nothing.
        self._key_cache: dict[str, tuple] = {}
        self._key_cache_lock = threading.Lock()
        # Bumped whenever a cached grant becomes invalid (the quota ran out). A
        # prefetch that was ALREADY IN FLIGHT when that happened carries a grant
        # issued under the old quota — clearing the dict cannot stop it, because it
        # lands afterwards and writes itself back in. It then hands a spent free
        # account a VOICED (paid) engine on the next Start, which we pay for and
        # the user gets billed past 100%. The epoch is the fix: a prefetch may only
        # publish if the world has not moved under it.
        self._key_epoch = 0
        # Idle-only sound-check probe ("do I hear this device?"): a loopback
        # capture whose only output is a peak level for the UI meter. Never runs
        # alongside a session (see soundcheck_start / _start).
        self._sc = None
        self._sc_level = 0.0
        self._sc_mic = None
        self._sc_mic_level = 0.0
        self._sc_timer = None
        self._sc_routing = None
        # One-time move of transcripts from the old (virtualized) AppData location
        # to the user-facing default. Best-effort; never blocks startup.
        self._migrate_transcripts()
        # LAST: every field _dispatch_loop reads now exists.
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="voxis-ui-dispatch")
        self._dispatch_thread.start()

    def _dispatch_loop(self):
        """Sole owner of the evaluate_js push channel, and of the OBS file write.

        WHY THIS THREAD EXISTS: pywebview's EdgeChromium evaluate_js is
        SYNCHRONOUS -- it Invokes onto the WebView2 UI thread and blocks the
        caller on a semaphore until the script has run and its result marshalled
        back (webview/platforms/edgechromium.py). _put_event used to call it
        inline, so every caption token blocked whichever thread produced it.

        That thread is the translator's receive loop, and it is the SAME loop
        that hands us translated audio: Gemini alternates audio and text parts in
        one `async for` (translator.py `_receive_loop`), and Qwen dispatches
        `response.audio.delta` and `response.audio_transcript.delta` from one
        `async for` too (qwen_translator.py). So a busy or slow JS frame delayed
        the NEXT audio chunk reaching the stager and the Player ring -- and Qwen
        is realtime-paced, meaning that ring runs with essentially no headroom
        (the 180 ms prefill in audio_io.Player exists precisely because of it).
        Gemini delivers a turn faster than realtime and could absorb the stall;
        Qwen could not. Cascade differs again -- its audio comes off a separate
        synth thread -- but the same block delayed sentences reaching that
        thread's queue.

        Everything here is therefore off the audio path. Ordering is preserved
        because this is a single FIFO consumer.
        """
        import json
        while not self._dispatch_stop.is_set():
            try:
                msg = self._push_q.get(timeout=0.1)
            except queue.Empty:
                msg = None
            if msg is not None:
                win = getattr(self, "_main_window", None)
                # No window yet (early startup) -> drop it here; poll() still
                # delivers it from _events once the UI is up.
                if win is not None:
                    try:
                        win.evaluate_js(
                            f"if(window.onVoxisEvent) window.onVoxisEvent({json.dumps(msg)});")
                    except Exception:
                        pass
            self._flush_obs()

    # ---------- callbacks from audio threads ----------
    # (The old public push_event() is gone: _put_event is the only publisher, so
    # everything on _push_q is guaranteed to be a {seq, ev} message. A second
    # entry point that enqueued a bare event would have silently bypassed the
    # sequence numbering the UI dedupes on.)
    @staticmethod
    def _enqueue(q, item):
        """put_nowait, dropping the OLDEST on overflow. The UI shows a live
        stream, so the freshest events win; and no audio thread may ever block
        on a full queue."""
        try:
            q.put_nowait(item)
            return
        except queue.Full:
            pass
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass

    def _put_event(self, ev):
        """Publish a UI event on both channels: the instant push (dispatcher
        thread) and the poll queue (backstop for a window that is not up yet, or
        a push that was dropped under overflow).

        Each event carries a monotonic `seq` so the UI can drop the second copy
        by IDENTITY. It used to dedupe on the event's CONTENT
        (`type + JSON.stringify(payload)`), which silently swallowed any
        genuinely repeated event: two identical caption deltas in a row (`" "`,
        `","`, a repeated word) lost the second one, and the fixed-payload
        events -- ("quota_refresh", None), ("quota_wall", None),
        ("review", None), ("daily_wall", None) -- could only ever fire once per
        dedupe window."""
        with self._seq_lock:
            self._event_seq += 1
            msg = {"seq": self._event_seq, "ev": list(ev)}
        self._enqueue(self._push_q, msg)
        self._enqueue(self._events, msg)

    def _on_text(self, direction, text, leg="incoming"):
        # Meeting mode runs two translator receiver threads into this one method;
        # serialize so their read-modify-write on the shared transcript / overlay /
        # OBS state cannot interleave (which previously mispaired source vs
        # translation in exports and let both threads truncate the OBS file).
        # `leg` says WHICH conversation side this text belongs to — the lock keeps
        # the buffers consistent, only the leg keeps the two sides apart.
        with self._text_lock:
            self._on_text_locked(direction, text, leg)

    def _on_speaker(self, label: int):
        """Speaker-change event from the local tracker (its worker thread).

        Splits the in-flight source utterance at the change so its words stay
        with the voice that (mostly — detection lags the true boundary by a
        couple of seconds) said them, tags subsequent source with the new
        label, and arms a soft break on the translated stream so back-to-back
        speakers stop merging into one caption line (see _on_text_locked)."""
        with self._text_lock:
            if label == self._cur_spk:
                return
            prev = self._cur_spk
            self._cur_spk = label
            self._spk_seen.add(label)
            if prev is None:
                return  # first assignment — nothing to split yet
            # The tracker only listens to the INCOMING capture, so it may only
            # ever split that leg's stream. The outgoing leg is the user's own
            # single voice and is never labeled.
            st = self._legs["incoming"]
            buf = st.src_buf.strip()
            if buf:
                st.src_done.append((st.src_spk, buf, st.last_src_t))
                st.src_buf = ""
                st.src_marks = []
            st.pending_spk_break = True

    def _peek_spk(self) -> int | None:
        """Best-effort label for the translation line streaming NOW: the oldest
        unpaired source utterance's speaker (FIFO pairing), else the in-flight
        buffer's. Only meaningful once ≥2 speakers were seen. Caller holds
        _text_lock."""
        if len(self._spk_seen) < 2:
            return None
        st = self._legs["incoming"]
        if st.src_done:
            return st.src_done[0][0]
        return st.src_spk if st.src_buf else self._cur_spk

    def _on_text_locked(self, direction, text, leg="incoming"):
        now = time.time()
        st = self._legs.get(leg) or self._legs["incoming"]
        if direction == "in":
            # Input transcription (what the speaker said). Accumulate per utterance
            # so a completed source can be paired with the translation turn it
            # produced. No UI event here — the source caption is attached when the
            # matching translation turn finalizes.
            if st.src_buf and (now - st.last_src_t) > LINE_GAP:
                # A speech pause completed this source utterance — queue it for the
                # translation turn it produced. Source leads the translation by the
                # model's ear-voice lag, so it is queued before that turn finalizes.
                # Tagged with the label the buffer STARTED under: this finalize
                # runs on the NEXT utterance's first token, by which time
                # _cur_spk may already be the next voice. Stamped with when this
                # utterance was last actually heard (_last_src_t), not "now" (the
                # moment the gap was merely detected) — that's what _pop_source
                # compares against a turn's own start time.
                st.src_done.append((st.src_spk, st.src_buf.strip(), st.last_src_t))
                st.src_buf = ""
                st.src_marks = []
            if not st.src_buf:
                # Only the incoming capture is diarized; the outgoing leg is the
                # user's own single voice.
                st.src_spk = self._cur_spk if leg == "incoming" else None
            st.src_buf += text
            st.src_marks.append((now, len(st.src_buf)))
            st.last_src_t = now
            self._track_source(now, text, leg)
            # Live "heard now" feed: the accumulating source utterance streams to
            # the UI's ghost line as it is spoken (the definitive, paired source
            # still lands with the 'src' event when its translation finalizes —
            # source LEADS translation by the ear-voice lag, so the live text
            # must not be attached to the currently rendering turn).
            # The ghost line shows what is being HEARD; the user's own speech is
            # not "heard" in that sense, so only the incoming leg feeds it.
            if leg == "incoming":
                self._put_event(("hear_live", st.src_buf.strip()))
            return
        # direction == "out": the translated text stream.
        if not self._session_start:
            # Fallback anchor only. _start sets this to the session's wall-clock
            # start so cue offsets match the recording; this covers text arriving
            # with no session behind it (tests drive _on_text directly).
            self._session_start = now
        gap = now - st.last_t
        # An armed speaker break fires at the next micro-pause: the model gives
        # no word timestamps, so the change cannot split the stream exactly —
        # the short output pause between the two voices' translations is the
        # best available seam.
        # Safety valves. LINE_GAP alone assumes the engine pauses between
        # utterances; a simultaneous engine streaming continuously never gives it
        # that pause, so a single turn can swallow 20+ seconds of speech (a field
        # session produced 548 characters in one caption line). Prefer a sentence
        # boundary; fall back to a hard ceiling so a run-on cannot grow forever.
        held = now - st.turn_start if st.turn_start else 0.0
        overlong = (len(st.cur_line) >= MAX_LINE_CHARS
                    or held >= MAX_LINE_SECONDS)
        newline = bool(st.cur_line) and (
            gap > LINE_GAP
            or (st.pending_spk_break and gap > SPK_GAP)
            or (overlong and st.cur_line.rstrip().endswith(SENTENCE_END))
            or len(st.cur_line) >= HARD_LINE_CHARS)
        if newline:
            # Repair before anything reads the line: the cross-turn re-speak
            # guard, the record and the exports must all see the same text.
            finished = _strip_inline_repeat(st.cur_line.strip())
            st.cur_line = ""
            # The turn that just ended pairs with — and consumes — only the
            # source heard up to roughly SRC_LAG_S ago, not whatever has
            # piled up in the buffer by now. Translation trails source by the
            # model's simultaneous-interpretation lag, so by the time this
            # turn's OUTPUT finishes, the source stream has already moved on
            # to content driving a LATER turn; grabbing "everything buffered
            # right now" over-claims into whichever turn happens to finish
            # first. See SRC_LAG_S for why this lag-adjusted "now" is used
            # instead of this turn's own start time.
            spk, src = self._pop_source(now - SRC_LAG_S, st)
            own_src = src or None
            if own_src:
                # The label rides along only in a genuinely multi-speaker
                # session (same ≥2 gate as _peek_spk), so a lone speaker is
                # never tagged "S1" on screen. The JSON turn keeps the raw
                # label either way — export renderers apply the same gate.
                self._put_event(("src", own_src,
                                 spk if len(self._spk_seen) >= 2 else None, leg))
            # Engine re-speak guard: after an internal reconnect Gemini can
            # re-emit the tail utterance, producing two identical consecutive
            # turns (field transcript 2026-07-10, t=39s). A long turn that
            # exactly repeats the previous one is that artifact, not real
            # speech — keep the first, drop the echo. Short exact repeats
            # ("Evet." twice) are plausible dialogue and stay.
            #
            # Matched on a NORMALIZED form: the re-speak is regenerated, not
            # replayed, so it comes back lightly reworded — a leading connective
            # or different punctuation defeated exact equality and let the echo
            # through ("rezidans temel olarak 10 haftalık…" twice in a field
            # session, spoken only once).
            # Compared against this LEG's own previous turn: in a meeting the two
            # sides interleave in the shared list, and the other side's line is
            # never this side's echo.
            prev = self._last_turn_text(leg)
            dup = len(finished) >= 20 and bool(prev) and _near_duplicate(prev, finished)
            # Record the finalized turn with its start offset and paired source.
            if finished and not dup:
                self._lines.append(finished)
                self._last_line = finished   # survives stop(); see Bridge.__init__
                turn = {
                    "t": max(0.0, st.turn_start - self._session_start),
                    "dir": "out",
                    "src": own_src,
                    "text": finished,
                }
                if spk is not None:
                    turn["spk"] = spk
                # Schema-additive, and only in a meeting: a Video/Game record must
                # stay byte-identical to what it was before legs existed.
                if getattr(self.controller, "mode", None) == "meeting":
                    turn["leg"] = leg
                self._turns.append(turn)
        if not st.cur_line:
            # Mark when this (new) turn began so its cue start is the speech
            # onset, not the moment it finalized one LINE_GAP later. A fresh
            # turn boundary also satisfies any armed speaker break.
            st.turn_start = now
            st.pending_spk_break = False
        st.cur_line += text
        st.last_t = now
        self._track_audio(now)
        line = st.cur_line.strip()
        # Speaker labels come from the incoming capture only.
        hint = self._peek_spk() if leg == "incoming" else None
        if hint is not None:
            line = f"S{hint}: {line}"
        # The overlay and the OBS file are single-line surfaces: the OTHER party
        # is what the user needs read back to them, so the outgoing leg (their
        # own words) never takes them over.
        if leg == "incoming":
            self._overlay_text = line
            self._overlay_until = now + FADE_MS
            self._obs_write(line)
        # Backlog only matters to the client when a NEW caption line is about
        # to appear (see index.html onTrans) — skip the stager read otherwise.
        backlog = self.controller.current_playback_backlog() if newline else 0.0
        self._put_event(("trans", text, newline, hint, backlog, leg))

    SRC_TRACK_MERGE_S = 1.0        # coalesce increments closer than this
    SRC_TRACK_MAX = 4000           # bound the record; a long session stays sane

    def _track_audio(self, now: float) -> None:
        """Sample how much translated speech has been produced, on the caption
        clock. Caller holds _text_lock.

        The caption stream was already recorded; the audio stream was not, so a
        session that SPOKE less than it CAPTIONED (a measured 968 spoken words
        against 1067 captioned) left no evidence of where the difference went.
        Sampling here rather than on a timer keeps it free of new threads and
        puts the samples exactly where they matter — while text is flowing."""
        if not self._session_start:
            return
        fn: Callable[[], float] | None = getattr(self.controller, "translated_audio_seconds", None)
        if not callable(fn):
            return
        try:
            sec = float(fn())
        except Exception:
            return                          # instrumentation must never break a session
        t = max(0.0, now - self._session_start)
        last = self._audio_track[-1] if self._audio_track else None
        if last is not None and t - last["t"] <= self.SRC_TRACK_MERGE_S:
            last["sec"] = sec               # same bucket: keep the latest total
            return
        if len(self._audio_track) >= self.SRC_TRACK_MAX:
            return
        self._audio_track.append({"t": t, "sec": sec})

    def _track_source(self, now: float, text: str, leg: str) -> None:
        """Record a source increment with the time it ARRIVED. Caller holds
        _text_lock.

        Deltas land a few words at a time, so consecutive ones are merged into
        the entry they continue — the useful resolution is "when did this
        stretch of source arrive", not one row per token."""
        text = text or ""
        if not text.strip() or not self._session_start:
            return
        t = max(0.0, now - self._session_start)
        last = self._src_track[-1] if self._src_track else None
        if (last is not None and last.get("leg") == (leg if leg != "incoming" else None)
                and now - last["_at"] <= self.SRC_TRACK_MERGE_S):
            last["text"] += text
            last["_at"] = now
            return
        if len(self._src_track) >= self.SRC_TRACK_MAX:
            return
        entry = {"t": t, "text": text, "_at": now}
        if leg != "incoming":
            entry["leg"] = leg
        self._src_track.append(entry)

    def _last_turn_text(self, leg: str) -> str:
        """Text of the most recent turn recorded for `leg`. Caller holds
        _text_lock."""
        for turn in reversed(self._turns):
            if turn.get("leg", "incoming") == leg:
                return turn.get("text", "")
        return ""

    def _pop_source(self, cutoff: float | None = None,
                    st: "_LegState | None" = None) -> tuple[int | None, str]:
        """(speaker, text) for the translation turn that just finalized.

        `cutoff` is `now - SRC_LAG_S` (see that constant), captured by the
        caller. Only source heard by `cutoff` is returned; source heard after
        it is left queued for a LATER turn instead of being claimed by this
        one. Consumed so it cannot be re-emitted. Caller holds _text_lock.

        `cutoff=None` (session stop, in _flush_turns) takes everything
        remaining unconditionally — there is no later turn to hand it off to.

        Still approximate — SRC_LAG_S is a fixed estimate of a lag that
        actually varies a little turn to turn, and the model gives no
        word-level timestamps to do better — but a lag-adjusted "now" is a
        far closer proxy to "how far the source has actually progressed" than
        the previous cutoff-free version, which handed whatever the source
        stream had reached by the time output happened to pause —
        systematically over-claiming into the turn that finished first."""
        st = st if st is not None else self._legs["incoming"]
        while st.src_done:
            spk, src, ts = st.src_done[0]
            if cutoff is not None and ts > cutoff:
                break  # not yet "reached" by this turn — leave queued
            st.src_done.pop(0)
            src = src.strip()
            if src:
                return spk, src
        if cutoff is None:
            src = st.src_buf.strip()
            st.src_buf = ""
            st.src_marks = []
            return (st.src_spk if src else self._cur_spk), src
        if not st.src_buf or not st.src_marks:
            return st.src_spk, ""
        split_len, idx = 0, 0
        for i, (ts, ln) in enumerate(st.src_marks):
            if ts > cutoff:
                break
            split_len, idx = ln, i + 1
        if split_len <= 0:
            return st.src_spk, ""
        src = st.src_buf[:split_len].strip()
        st.src_buf = st.src_buf[split_len:]
        st.src_marks = [(ts, ln - split_len) for ts, ln in st.src_marks[idx:]]
        return st.src_spk, src

    def _pending_source(self, st: "_LegState | None" = None) -> str:
        """All source not yet paired to a turn (queue + in-flight buffer), for the
        stop-time flush of a source-only session. Caller holds _text_lock."""
        st = st if st is not None else self._legs["incoming"]
        parts = [s for _, s, _ts in st.src_done if s.strip()]
        if st.src_buf.strip():
            parts.append(st.src_buf.strip())
        return " ".join(parts).strip()

    def _emit_status(self, msg, level="info"):
        """Push a status line to the UI.

        Carries an explicit level so the front end (and the error badge) never
        has to infer severity by sniffing a localized 'HATA:'/'ERROR' prefix.
        The legacy positional payload (the message string) is preserved so the
        existing JS poll handler keeps working; the structured fields ride
        alongside for callers that read them."""
        # Raw engineering diagnostics (the "capture: backend=..." line, the
        # translator stall/clone notices) go to voxis.log + the problem-report
        # tail below — never to the user-facing transcript.
        diagnostic = isinstance(msg, str) and msg.startswith(("capture: ", "translator: "))
        if diagnostic:
            logging.getLogger("voxis").info(msg)
        else:
            self._put_event(("status", msg, {"level": level, "msg": msg}))
        # Keep a bounded tail for the problem-report diagnostics (raw text; it is
        # scrubbed again at report-assembly time).
        if isinstance(msg, str) and msg:
            self._status_log.append(msg)
            if len(self._status_log) > 40:
                del self._status_log[:-40]
        if level == "error":
            self._badge = (t("badge_error"), "#fb7185", "err")

    def _on_status(self, msg):
        # ModeController only forwards a localized string. Treat its events as
        # informational; error-badge state is set explicitly by the paths that
        # actually fail (e.g. _start), not by parsing a translated prefix.
        self._record_session_event(msg)
        self._emit_status(msg, "info")

    def _record_session_event(self, msg):
        """Keep an engine-lifecycle line in the session record.

        This channel carries only ModeController/translator events (connect,
        rotation, reconnect, watchdog trips), so everything arriving here belongs
        in the saved transcript. Bounded: a flapping link must not grow the record
        without limit — the oldest entries are the least interesting once a
        session has been dropping for a while."""
        if not isinstance(msg, str) or not msg.strip():
            return
        with self._text_lock:
            if not self._session_start:
                return                      # no active session — nothing to anchor to
            self._session_events.append({
                "t": max(0.0, time.time() - self._session_start),
                "msg": msg,
            })
            if len(self._session_events) > 200:
                del self._session_events[:-200]

    def _on_usage_reported(self):
        self._put_event(("quota_refresh", None))

    def _on_quota_exceeded(self):
        """Server reported the license is exhausted (402 on /usage/report). The
        server isn't in the audio path, so the cutoff is enforced here.

        For a free tier whose taste just ran out the cutoff is a HANDOVER, not a
        wall — but an explicit one. The first design swapped engines under the
        live session, and in the field the owner heard the chip say "Pro voice"
        while Piper was speaking: with two engines inside one session, the UI and
        the audio can disagree. This design makes that state impossible: one
        session, one engine. The Pro voice finishes its sentence, the session
        stops, and a card asks whether to continue on the free voice — with the
        same last sentence replayable in BOTH voices, so the user hears exactly
        what they are choosing between (owner's design, 2026-07-13). "Continue"
        starts a NEW session, which the server routes to the cascade from the
        first frame — a path that runs in production already.

        The hard stop remains for everyone else: paid accounts out of minutes,
        Meeting mode, a disabled cascade, a spent daily allowance.

        Three walls, not two. A 402 arriving while the CASCADE is the live engine
        can only be the daily allowance: the server's cascade heartbeat path never
        compares against the license quota at all (handlers/usage.go), it only
        books against the 10-min/day counter. Reading the engine — rather than the
        quota flags — is what tells the two apart, so someone already on the free
        voice is told "today's free minutes are up, they come back tomorrow"
        instead of being offered the free voice they are currently listening to
        (owner report, 2026-07-13).

        Runs on a usage-report worker thread; self.stop() dispatches teardown to
        its own thread under the session lock, so calling it here is safe."""
        # A key prefetched before the quota ran out must not let the next Start
        # sail past the paywall — drop it so the start re-asks the server. Bumping
        # the epoch under the same lock also disowns any prefetch still IN FLIGHT:
        # clearing alone left a race where that fetch (carrying a voiced grant from
        # when the user still had minutes) landed afterwards and put the PAID engine
        # back in the cache, which the next Start then spent. That is how a free
        # account kept running the paid engine past its taste — billed to the user
        # (>100% quota) and paid for by us (field data, 2026-07-13).
        with self._key_cache_lock:
            self._key_cache.clear()
            self._key_epoch += 1
        self._put_event(("quota_refresh", None))

        q = self._last_quota
        try:
            on_cascade = self.controller.current_engine() == "cascade"
        except Exception:
            # Never let an engine read cost us the quota snapshot: without it the
            # free tier would fall through to the PAID paywall.
            on_cascade = False

        if on_cascade:
            # The daily wall. Not an error, and not the taste wall: the free voice
            # is not taken away, it just comes back tomorrow.
            self._last_error_code = None
            self._emit_status(t("st_daily_free_done"), "warn")
            self._drain_tts()
            self.stop()
            self._put_event(("daily_wall", None))
            return

        try:
            free_open = q.get("cascade_available") if isinstance(q, dict) else None
            if free_open is None and isinstance(q, dict):
                # Server predates cascade_available (deploy order: server first,
                # but never assume it). Fall back to the old flag.
                free_open = q.get("cascade_ready") is True
            wall_free = (free_open is True and self.controller.mode != "meeting")
        except Exception:
            wall_free = False
        if wall_free:
            mode = self.controller.mode
            # Not an error: the taste simply ended. Leaving _session_error unset
            # also keeps the rating prompt honest about clean sessions.
            self._last_error_code = None
            self._emit_status(t("st_taste_wall"), "warn")
            self._drain_tts()          # let the Pro voice finish its sentence
            self.stop()
            self._put_event(("taste_wall", {"mode": mode}))
            return

        self._last_error_code = "st_quota_exceeded"
        self._session_error = True
        self._emit_status(t("st_quota_exceeded"), "warn")
        # Raise the in-app paywall card at the mid-session cutoff (the highest-
        # intent moment) instead of a silent stop. JS reads the live QUOTA global
        # for the number; this only fires once per session (guarded upstream).
        self._put_event(("quota_wall", None))
        self.stop()

    def _drain_tts(self, timeout: float = 8.0):
        """Let the paid voice finish what it has already produced before the
        session closes. Stopping the translator first means no NEW audio arrives;
        the player's ring then plays out its last sentence and goes quiet. Cutting
        instead of draining would clip the goodbye mid-word — and that clipped
        word is the last impression of the paid tier the user gets."""
        inc = self.controller.incoming()
        if inc is None:
            return
        try:
            inc.translator.stop()
        except Exception:
            pass
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                player_active = bool(inc.player.tts_active)
                stager = getattr(inc, "_stager", None)
                staged = float(stager.backlog_s) if stager is not None else 0.0
                if not player_active and staged <= 0.02:
                    break
                time.sleep(0.2)
        except Exception:
            pass

    def _on_session_failed(self):
        """A translator thread died mid-session (terminal error / retries
        exhausted). Billing already stopped via _is_session_live; tear the session
        down so capture, ducking and the endpoint redirection are released and the
        badge isn't a false green. Mirrors _on_quota_exceeded; stop() is
        self-dispatching so calling it from the heartbeat thread is safe.

        Uses its own st_session_failed string (NOT st_capture_lost): a dead
        translator is a connection failure, and mislabeling it as a capture
        fault poisons field diagnosis (error_reason rides into problem reports)."""
        self._last_error_code = "st_session_failed"
        self._session_error = True
        self._emit_status(t("st_session_failed"), "error")
        self.stop()

    def _obs_write(self, text):
        """Stage the OBS subtitle line. Called per token from the translator's
        receive thread, so it only formats and parks the payload — the actual
        file write happens on the dispatcher thread (_flush_obs), off the path
        that also carries translated audio."""
        if not self.cfg.get("obs_subtitle_enabled"):
            return
        # Cap the CAPTION first so SUBTITLE_MAX still bounds the spoken line; the
        # badge is appended afterward as its own row and is exempt from the cap.
        text = _cap_subtitle(text)
        out = text
        if self._show_badge():
            out = f"{text}\n{t('powered_by')}"
        with self._obs_lock:
            self._obs_pending = out

    def _flush_obs(self):
        """Write the staged OBS line, if it changed. Dispatcher thread only.

        Only rewrite when the content actually changed — the translation stream
        repaints the same line on every token, and an OBS text source re-reads on
        file mtime, so skipping no-op writes avoids needless flicker/IO. The
        dedupe key is the full payload (caption + badge) so toggling the badge or
        switching UI language forces one repaint."""
        with self._obs_lock:
            out = self._obs_pending
            self._obs_pending = None
        if out is None or out == self._last_obs_write:
            return
        try:
            with open(OBS_FILE, "w", encoding="utf-8") as f:
                f.write(out)
            self._last_obs_write = out
        except OSError:
            pass

    # ---------- JS-facing API ----------
    def get_init(self):
        outs = list_device_names("output") or ["—"]
        mics = list_device_names("input")
        from . import byok_store
        from .config import resolve_engine
        uid = self._ensure_user_id()
        engines = self._engine_options()  # gemini-only
        byok_status = {e: (byok_store.has_byok(uid, e) if uid else False) for e in engines}
        byok_set = byok_status.get("gemini", False)  # back-compat: single bool
        from .paths import client_channel
        self._maybe_check_app_manifest()
        qwen_voiced = _voice_choice_langs(self.cfg)
        return {
            "version": APP_VERSION,
            "channel": client_channel(),
            "outputs": [t("default_mic"), *outs],
            "mics": [t("default_mic"), *mics],
            "langs": LANGS,
            # Targets the FREE tier can actually speak. It translates all 79 but
            # only voices those with a registered Piper voice, so the picker can
            # say so up front instead of letting a free user discover the
            # silence mid-session. Paid engines voice every target; the JS only
            # consults this when the licence is on the free tier.
            "voiced_langs": _free_voiced_langs(),
            # Targets whose translated voice can be GENDERED. Only the Qwen-routed
            # ones qualify: the Gemini translate model ignores the voice field
            # entirely (measured 2026-07-30 — five valid names and a garbage name
            # all returned the same voice, and the garbage name was not rejected).
            # Computed here with the engine's own predicate, over the real picker
            # list, so the UI never has to re-implement BCP-47 normalization and
            # cannot drift from routing (which the server can also override).
            "voice_choice_langs": qwen_voiced,
            # Targets a FREE-tier session (incl. the one-time Pro taste) may
            # pick at all — Qwen's voiced tier, same list as voice_choice_langs
            # above (identical predicate: qwen_can_voice). A free session must
            # never reach Gemini (2026-08-12 cost-pressure policy — see
            # .vault/decision-log.md), so the picker locks everything outside
            # this list for a free/taste account instead of letting the user
            # pick it and hit a late "unavailable" from _resolve_saas. Paid
            # accounts ignore this entirely (Gemini catch-all still serves
            # them for these targets, unchanged).
            "free_engine_langs": qwen_voiced,
            # The prepacked term list, so Settings can show exactly what ships
            # instead of a second copy that could drift from config.DEFAULT_TERMS.
            "builtin_terms_list": list(DEFAULT_TERMS),
            "profiles": [[k, t(f"profile_{k}")] for k in ("custom", "meeting", "film", "conference")],
            "qualities": self._quality_options(),
            "gemini_voices": GEMINI_VOICES,
            "byok_set": byok_set,
            "byok_status": byok_status,
            "engines": engines,
            "engine": resolve_engine(self.cfg),
            "official_release": IS_OFFICIAL_RELEASE,
            # Gates the JS custom-drag handler (index.html): Windows/WebView2
            # drags the frameless titlebar natively via the CSS
            # `-webkit-app-region: drag` region; WebKitGTK (Linux) doesn't, so
            # JS drives it there via win_get_pos/win_move_to instead. Wiring
            # the JS handler on Windows too would double-drag against the
            # native path.
            "is_linux": sys.platform.startswith("linux"),
            "badge_removable": self._badge_removable(),
            "onboarding_done": bool(self.cfg.get("onboarding_done", False)),
            "cfg": self._cfg_view(outs, mics),
        }

    def _maybe_check_app_manifest(self):
        """Kick off the one-shot, once-per-launch background check against
        voxislive.com/app.json (see voxis_client.fetch_app_manifest). Runs for
        BOTH build flavors — it's an unauthenticated GET, not telemetry — but
        stays entirely off the get_init return path: a slow/offline network
        must never delay first paint."""
        if self._manifest_check_started:
            return
        self._manifest_check_started = True
        threading.Thread(target=self._check_app_manifest, daemon=True).start()

    def _check_app_manifest(self):
        from . import voxis_client
        manifest = voxis_client.fetch_app_manifest()
        if not manifest:
            return
        latest = ((manifest.get("app") or {}).get("version") or "").strip()
        cur, new = _parse_semver(APP_VERSION), _parse_semver(latest)
        if cur is None or new is None or new <= cur:
            return
        self._put_event(("update_available", {"version": latest}))

    def _beta_allowed(self) -> bool:
        """Beta (Qwen) eligibility. Dev builds: always. Official: the server's
        per-account flag, refreshed by check_auth/verify. The Beta TAB was
        removed in 1.0.33 (Qwen graduated to the standard server-routed primary
        engine); the cfg["beta"] opt-in remains config-file-driven — the dev
        A/B path and older field builds keep working, and the server re-checks
        eligibility on session-key anyway."""
        if not IS_OFFICIAL_RELEASE:
            return True
        return bool(getattr(self, "_beta_flag", False))

    def _quality_options(self):
        """End-user build sees two friendly choices (smooth vs savings); the
        developer build sees the full preset list for tuning."""
        if IS_OFFICIAL_RELEASE:
            return [["balanced", t("quality_smooth")],
                    ["turbo", t("quality_fast")],
                    ["callout", t("quality_callout")],
                    ["max_savings", t("quality_saver")]]
        return [[k, t(f"quality_{k}")] for k in QUALITY_PRESETS]

    def _engine_options(self):
        """Engine choices for the selector. Gemini-only: Qwen is served by the
        SERVER's per-target routing (primary engine for its voiced targets),
        never a user-facing selector choice."""
        from .config import ENGINE_GEMINI
        return [ENGINE_GEMINI]

    # ---------- store ----------
    def open_store_page(self):
        """Open the Voxis Microsoft Store listing in the Store app. Updates are
        delivered by the Store itself; this is just a shortcut to the listing.
        No-op-safe: failures are swallowed so a missing Store app never raises."""
        url = "ms-windows-store://pdp/?productid=9P5Z0KVS58RS"
        try:
            os.startfile(url)  # Windows shell handles the ms-windows-store: scheme
            return {"ok": True}
        except Exception as e:
            _log.exception("open_store_page failed")
            return {"ok": False, "error": str(e)}

    def _cfg_view(self, outs=None, mics=None):
        outs = outs or list_device_names("output")
        mics = mics or list_device_names("input")
        c = dict(self.cfg)
        cur_out = self.cfg["devices"].get("headphones_output", "")
        cur_mic = self.cfg["devices"].get("microphone", "")
        c["devices"] = dict(self.cfg["devices"])
        c["devices"]["headphones_output_label"] = next(
            (n for n in outs if cur_out and cur_out.lower() in n.lower()), t("default_mic"))
        c["devices"]["microphone_label"] = next(
            (n for n in mics if cur_mic and cur_mic.lower() in n.lower()), t("default_mic"))
        # Resolved transcript folder for the Settings readout (the raw
        # cfg["transcript_dir"] may be "" = default; show where files actually go).
        c["transcript_dir_display"] = self._transcript_dir()
        return c

    def get_cfg(self):
        return self._cfg_view()

    def _save_cfg(self) -> bool:
        """Persist config, surfacing (not swallowing) a write failure so the UI
        can warn instead of silently losing the setting. Held under a lock so
        concurrent bridge threads (e.g. a slider drag) can't race on the file."""
        try:
            with self._save_lock:
                save_config(self.cfg)
            return True
        except OSError:
            _log.exception("config save failed")
            self._emit_status(t("err_save_failed"), "error")
            return False

    def set_hotwords(self, text):
        """Persist the meeting-terms list into cfg["beta"]["hotwords"].

        Nested under `beta` because that is where the engine already reads it
        from (engines.py passes parse_hotwords(beta["hotwords"]) into every Qwen
        session, beta opt-in or not) — the pipeline has always been there, only
        the UI was missing. Written through a COPY so the other beta knobs
        (clone / source_lang / vad_ms) survive: they are config-file-only and a
        whole-dict overwrite would silently reset them.

        Restarts a running session, like the other engine-config settings: the
        term list rides the session handshake, so a live session cannot pick it
        up without one."""
        beta = dict(self.cfg.get("beta") or {})
        beta["hotwords"] = str(text or "")[:HOTWORDS_MAX_CHARS]
        self.cfg["beta"] = beta
        ok = self._save_cfg()
        self._maybe_restart()
        return ok

    def hotword_stats(self, text):
        """Term counts for the UI's limit hint: the user's own, the prepacked ones
        that still fit, and the total actually sent.

        Computed with the SAME merge the engine uses (config.merge_hotwords), so
        the number on screen cannot drift from what rides the session — including
        the case where the combined list is capped."""
        from .config import HOTWORDS_LIMIT, merge_hotwords
        text = str(text or "")
        builtin_on = bool(self.cfg.get("builtin_terms", True))
        user = len(parse_hotwords(text))
        total = len(merge_hotwords(text, builtin=builtin_on))
        return {"user": user, "builtin": max(0, total - user),
                "total": total, "limit": HOTWORDS_LIMIT}

    def set_voice_gender(self, leg, gender):
        """Persist the requested voice gender for one leg and restart if live.

        Both arguments are allow-listed: this is a JS-reachable door into the
        config, and the value ends up in a session handshake where an unknown
        voice name would strand the engine (see qwen_translator's module
        docstring). Restarts a running session because the voice is chosen at
        connect time — same reason set_hotwords does."""
        from .config import VOICE_GENDERS
        key = {"incoming": "voice_gender_incoming",
               "outgoing": "voice_gender_outgoing"}.get(str(leg))
        if key is None or str(gender) not in VOICE_GENDERS:
            return False
        if self.cfg.get(key) == gender:
            return True          # no-op: never restart a session for nothing
        self.cfg[key] = str(gender)
        ok = self._save_cfg()
        if ok:
            self._maybe_restart()
        return ok

    def whatsnew(self):
        """Release notes to show ONCE after an update, in the UI language.

        Covers EVERY version the user skipped, not just the running one. Store
        updates land in the background and skip versions freely — someone can go
        from 1.0.49 to 1.0.52 in one step — and showing only the running version
        made every release in between invisible (1.0.50's notes reached nobody
        who jumped 1.0.49 -> 1.0.51 that way).

        Returns None when there is nothing to show: already seen, no notes for
        anything unread, or a first-ever run. The fresh-install case is marked
        seen silently — a brand-new user gets the onboarding tour, and a
        changelog for versions they never ran would be noise."""
        from . import whatsnew as wn
        seen = str(self.cfg.get("whatsnew_seen", ""))
        if seen == APP_VERSION:
            return None
        if not self.cfg.get("onboarding_done", False):
            self.mark_whatsnew_seen()
            return None
        entries = wn.entries_since(seen, i18n.current_language(), APP_VERSION)
        if not entries:
            # Nothing written for anything unread (a release can forget its
            # notes). Degrade to the old silence rather than an empty dialog —
            # and do NOT mark seen, so the next release's card still opens.
            return None
        return {"version": APP_VERSION, "entries": entries}

    def mark_whatsnew_seen(self):
        """Record that this version's notes were shown. Separate from mark_seen:
        that door writes booleans, this one stores a version string so the next
        update opens the card again."""
        self.cfg["whatsnew_seen"] = APP_VERSION
        return self._save_cfg()

    # The only keys the generic set_cfg() escape hatch may write. Anything with
    # its own dedicated, validated setter (transcript_dir -> choose_transcript_dir,
    # hotwords -> set_hotwords, voice gender -> set_voice_gender, device ->
    # set_device, profile -> set_profile...) is deliberately absent here even
    # though it is a real cfg key elsewhere — set_cfg must not become a second,
    # unvalidated way to write it. Keep in sync with every literal key app.js
    # passes to api().set_cfg(...) (tests/test_js_api_facade.py-style drift
    # would be silent otherwise: an unlisted key here just gets ignored).
    _SET_CFG_ALLOWED_KEYS = frozenset((
        "ui_theme", "ui_language", "target_language_incoming",
        "target_language_outgoing", "duck_gain", "tts_volume",
        "show_subtitles", "obs_subtitle_enabled", "record_audio",
        "auto_export_txt", "auto_export_srt", "auto_export_vtt",
        "speaker_labels", "builtin_terms", "allow_multiple_instances",
        "monitor_outgoing_translation", "branding_badge_enabled",
        "meeting_consent_ack",
        # Not currently wired to a UI control, but already handled specially
        # below and legitimate to keep accepting (dev/A-B knobs).
        "quality_preset", "engine", "gemini_voice",
    ))

    def set_cfg(self, key, value):
        if key not in self._SET_CFG_ALLOWED_KEYS:
            _log.warning("set_cfg: rejected unlisted key %r", key)
            return False
        # The attribution badge can only be turned off by a paid subscriber;
        # silently ignore a disable attempt from a free/OSS user (defense-in-depth
        # behind the already-disabled UI toggle).
        if key == "branding_badge_enabled" and not value and not self._badge_removable():
            value = True
        self.cfg[key] = value
        if key == "ui_language":
            i18n.set_language(str(value))
        if key == "duck_gain":
            self.controller.set_duck_gain(float(value))
            self._mark_custom()
        elif key == "tts_volume":
            self.controller.set_tts_volume(float(value))
        elif key in ("quality_preset", "target_language_incoming",
                     "target_language_outgoing", "gemini_voice", "engine",
                     "monitor_outgoing_translation",
                     # The prepacked term list rides the session handshake, so a
                     # live session has to be rebuilt to pick it up (same reason
                     # set_hotwords restarts).
                     "builtin_terms"):
            if key == "quality_preset":
                self._mark_custom()
            if key == "target_language_incoming":
                # New target = new per-target engine routing: warm its key so
                # the next Start (or the restart below) skips the issuance RTT.
                self._prefetch_session_key()
            self._maybe_restart()
        return self._save_cfg()

    def swap_languages(self):
        """Atomically exchange the two translation targets.

        The center arrow looks like one action, so persist and restart only once;
        two concurrent ``set_cfg`` calls would race config writes and could
        rebuild a live Meeting session twice.
        """
        incoming = self.cfg.get("target_language_incoming", "")
        outgoing = self.cfg.get("target_language_outgoing", "")
        self.cfg["target_language_incoming"] = outgoing
        self.cfg["target_language_outgoing"] = incoming
        ok = self._save_cfg()
        if not ok:
            self.cfg["target_language_incoming"] = incoming
            self.cfg["target_language_outgoing"] = outgoing
            return {"ok": False, "incoming": incoming, "outgoing": outgoing}
        self._prefetch_session_key()
        self._maybe_restart()
        return {"ok": True, "incoming": outgoing, "outgoing": incoming}

    # ---------- attribution badge gating ----------
    def _is_paid(self) -> bool:
        """True only for an official build with an active PAID license. Free
        tiers, unknown/unreachable quota, and the OSS build all return False, so
        the 'Powered by Voxis' badge stays on (removing it is a paid perk)."""
        if not IS_OFFICIAL_RELEASE:
            return False
        q = self._last_quota
        if not isinstance(q, dict):
            return False
        if q.get("unlimited"):
            return True
        tier = str(q.get("tier") or q.get("plan") or "").strip().lower()
        return tier in ("creator", "pro", "enterprise", "premium", "paid")

    def _taste_active(self) -> bool:
        """True for a free/non-paid account still inside its one-time 15-minute
        Pro taste — the population the Qwen-failure cascade rescue exists for
        (pipeline._swap_to_cascade). False for a paid account (gets the Gemini
        failover instead — see _is_paid), an unknown/unreachable quota (fails
        closed: no client-side rescue attempt rather than a guess — the server
        re-checks eligibility from scratch at the moment of use regardless),
        and an already-spent taste (that account's cascade is the ordinary
        daily one, not this path)."""
        if not IS_OFFICIAL_RELEASE or self._is_paid():
            return False
        return not self._taste_spent()

    def _badge_removable(self) -> bool:
        """Whether the user may turn the attribution badge off (paid only)."""
        return self._is_paid()

    def _show_badge(self) -> bool:
        """Effective overlay/OBS attribution visibility: paid users honor their
        Settings toggle; everyone else always shows it."""
        if not self._badge_removable():
            return True
        return bool(self.cfg.get("branding_badge_enabled", True))

    def set_profile(self, name):
        apply_profile(self.cfg, name)
        ok = self._save_cfg()
        self._maybe_restart()
        return ok

    def _is_default_device(self, name) -> bool:
        """True when the UI returned a default-device entry. Matches the empty
        sentinel and the localized label rather than the Turkish literal so a
        non-TR UI maps back to the system default correctly."""
        return not name or name == t("default_mic")

    def set_device(self, kind, name):
        if kind == "output":
            self.cfg["devices"]["headphones_output"] = (
                DEFAULT_DEVICE if self._is_default_device(name) else name)
        else:
            self.cfg["devices"]["microphone"] = (
                DEFAULT_DEVICE if self._is_default_device(name) else name)
        ok = self._save_cfg()
        self._maybe_restart()
        return ok

    def _ensure_user_id(self) -> str | None:
        """Resolves the BYOK store identifier from the JWT payload locally.

        Independent of license/quota state so an unlicensed user can still
        persist their own API key.
        """
        if not IS_OFFICIAL_RELEASE:
            return "developer"
        if self._user_id:
            return self._user_id
        from . import voxis_client
        self._user_id = voxis_client.user_id_from_jwt()
        return self._user_id

    def save_keys(self, gem):
        # Official-release builds never expose BYOK entry; refuse silently as
        # a defense-in-depth check.
        if IS_OFFICIAL_RELEASE:
            return False
        uid = self._ensure_user_id()
        if not uid:
            return False
        from . import byok_store
        current = byok_store.load_byok(uid)
        # OSS/BYOK is Gemini-only; preserve the previously stored value when blank.
        new_gem = gem.strip() if gem and gem.strip() else current.get("gemini", "")
        byok_store.save_byok(uid, new_gem)
        return True

    def clear_byok(self, engine=None) -> bool:
        if IS_OFFICIAL_RELEASE:
            return False
        uid = self._ensure_user_id()
        if not uid:
            return False
        from . import byok_store
        byok_store.clear_byok(uid, engine)
        return True

    # ---------- problem reporting ----------
    # User-initiated only: nothing here transmits without an explicit Send click
    # (the offline queue flushes a payload the user already consented to). The
    # whole feature is official-build-only — the OSS/BYOK build hard-gates the
    # network call in voxis_client.send_report, mirroring report_usage.
    def _build_diagnostics(self) -> dict:
        """Fixed allowlist of non-identifying technical context. Never dumps
        config.json or env — only these keys, scrubbed again before send."""
        import platform

        from .paths import client_channel
        cfg = self.cfg
        # Engine + model of the LIVE session (not the config selector) — the field
        # that actually answers "was this a Gemini or a Qwen-beta session?". Falls
        # back to the routed engine when idle.
        engine = ""
        try:
            engine = self.controller.current_engine() or ""
        except Exception:
            engine = ""
        try:
            from .config import resolve_model, route_engine
            if not engine:
                engine = route_engine(cfg, cfg.get("target_language_incoming", ""))
            model = resolve_model(cfg, engine or None)
        except Exception:
            model = cfg.get("model", "")
        beta = cfg.get("beta") or {}
        beta_enabled = bool(beta.get("enabled")) and self._beta_allowed()
        backend = "vbcable" if cfg.get("capture_backend", "driverless") == "vbcable" else "driverless"
        return {
            "app_version": APP_VERSION,
            "channel": client_channel(),
            "official": IS_OFFICIAL_RELEASE,
            "os": f"{platform.system()} {platform.release()}",
            "os_build": platform.version(),
            "arch": platform.machine(),
            "mode": getattr(self.controller, "mode", None) or "idle",
            "quality": cfg.get("quality_preset", ""),
            "engine": engine,
            "beta_enabled": beta_enabled,
            # Qwen-beta voice-clone mode: distinguishes "all speakers one voice by
            # design" (once) from "per-response clone failing" (always) when a
            # report complains voices collapsed — invisible without it.
            "beta_clone": (beta.get("clone", "off") if beta_enabled else ""),
            "beta_source": (beta.get("source_lang", "auto") if beta_enabled else ""),
            "model": model,
            "capture_backend": backend,
            "lang_target_incoming": cfg.get("target_language_incoming", ""),
            "lang_target_outgoing": cfg.get("target_language_outgoing", ""),
            "error_reason": self._last_error_code or "",
            "recent_status": list(self._status_log[-15:]),
        }

    def _collect_transcript(self) -> str:
        """Render the current session's paired turns as plain text. Only ever
        called when the user ticks the opt-in checkbox."""
        with self._text_lock:
            turns = list(self._turns)
        lines = []
        for tn in turns:
            src = (tn.get("src") or "").strip()
            txt = (tn.get("text") or "").strip()
            if src and txt:
                lines.append(src + "  ->  " + txt)
            elif txt:
                lines.append(txt)
            elif src:
                lines.append(src)
        return ("\n".join(lines))[:200000]

    def _collect_log_tail(self, max_bytes: int = 32768) -> str:
        """Tail of the app's own log (voxis.log — network/config errors). Scrubbed
        before it can leave the device. Auto-included so even a one-line or empty
        report still carries the diagnostic the engine recorded."""
        from . import report_scrub
        path = user_path("voxis.log")
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                data = f.read()
        except OSError:
            return ""
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return report_scrub.scrub_text(data)

    def _build_report_payload(self, form: dict) -> dict:
        """Assemble + scrub (scrub-v1) the report payload from the modal form.
        Secrets/PII are redacted here so they never leave the device."""
        import uuid

        from . import report_scrub
        from .paths import client_channel
        form = form or {}
        include_tx = bool(form.get("include_transcript"))
        message = (form.get("message") or "").strip()[:4000]
        repro = (form.get("repro") or "").strip()[:2000]
        # The reply email is purpose-bound (user typed it for a reply) — kept
        # as-is, not scrubbed; everything else is redacted.
        email = (form.get("email") or "").strip()[:200]
        payload = {
            "category": form.get("category") or "other",
            "severity": form.get("severity") or "normal",
            "message": report_scrub.scrub_text(message),
            "repro": report_scrub.scrub_text(repro),
            "email": email,
            "transcript_included": include_tx,
            "transcript": report_scrub.scrub_text(self._collect_transcript()) if include_tx else "",
            "diagnostics": report_scrub.scrub_value(self._build_diagnostics()),
            "log": self._collect_log_tail(),
            "correlation": uuid.uuid4().hex,
            "channel": client_channel(),
            "scrub_schema": report_scrub.SCRUB_SCHEMA,
        }
        return payload

    def preview_report(self, form: dict) -> dict:
        """Return the exact scrubbed payload that Send would transmit, for the
        modal's 'preview data to be sent' expander (transparency affordance)."""
        if not IS_OFFICIAL_RELEASE:
            return {}
        try:
            return self._build_report_payload(form)
        except Exception:
            self._log_report_error("preview")
            return {}

    def send_report(self, form: dict) -> dict:
        """JS -> Python: submit a problem report. Official-build only.

        Returns {ok, ticket?, deduped?} on success, {ok:False, queued:True} when
        the network is down (saved for explicit flush), or {ok:False, error}."""
        if not IS_OFFICIAL_RELEASE:
            return {"ok": False, "error": "disabled"}
        try:
            # Message is optional: the scrubbed app log + diagnostics are attached
            # automatically, so a one-click report still carries what we need.
            form = form or {}
            payload = self._build_report_payload(form)
        except Exception:
            self._log_report_error("build")
            return {"ok": False, "error": "internal"}
        from . import voxis_client
        res = voxis_client.send_report(payload)
        if res.get("ok"):
            return {"ok": True, "ticket": res.get("ticket", ""), "deduped": bool(res.get("deduped"))}
        if res.get("retryable"):
            self._queue_report(payload)
            return {"ok": False, "queued": True}
        return {"ok": False, "error": res.get("error", "failed")}

    def _report_queue_path(self) -> str:
        return user_path("reports_pending.json")

    def _queue_report(self, payload: dict) -> None:
        """Persist a report that couldn't be sent (network/5xx) for an explicit
        flush on next app start / next modal open. Capped + deduped by
        correlation so a retry can never double-file. Never transmits."""
        import json
        path = self._report_queue_path()
        try:
            queued = []
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    queued = json.load(f) or []
            corr = payload.get("correlation")
            queued = [q for q in queued if q.get("correlation") != corr]
            queued.append(payload)
            queued = queued[-10:]  # cap
            with open(path, "w", encoding="utf-8") as f:
                json.dump(queued, f)
        except Exception:
            self._log_report_error("queue")

    def flush_reports(self) -> int:
        """Send any queued reports. Called on startup and when the report modal
        opens — both are explicit user contexts (app launch / opening the form),
        never a silent background flush. Returns the count successfully sent."""
        if not IS_OFFICIAL_RELEASE:
            return 0
        import json
        path = self._report_queue_path()
        if not os.path.exists(path):
            return 0
        try:
            with open(path, encoding="utf-8") as f:
                queued = json.load(f) or []
        except Exception:
            return 0
        if not queued:
            return 0
        from . import voxis_client
        remaining, sent = [], 0
        for payload in queued:
            res = voxis_client.send_report(payload)
            if res.get("ok"):
                sent += 1
            elif res.get("retryable"):
                remaining.append(payload)  # keep transient failures for next time
            # non-retryable (400/disabled): drop — re-queueing would never succeed.
        try:
            if remaining:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(remaining, f)
            else:
                os.remove(path)
        except Exception:
            pass
        return sent

    def _log_report_error(self, where: str) -> None:
        try:
            from . import voxis_client
            voxis_client._log_detail("report:" + where, RuntimeError("report assembly/dispatch failed"))
        except Exception:
            pass

    def check_auth(self) -> dict:
        """Page-load auth check. Returns {authenticated, quota}. Non-blocking —
        uses the cached JWT for identity."""
        if not IS_OFFICIAL_RELEASE:
            return {"authenticated": True, "quota": None}
        from . import voxis_client
        # Top-of-funnel: the app is open. Fire once per process BEFORE the JWT
        # gate below, so users who launch but never sign in are still counted
        # (app_launched only fires post-auth). Anonymous, device-hash attributed.
        if not self._opened_reported:
            self._opened_reported = True
            voxis_client.report_app_opened_async()
        jwt = voxis_client.get_jwt()
        if not jwt:
            return {"authenticated": False, "quota": None}
        self._user_id = voxis_client.user_id_from_jwt()
        info, err = voxis_client.verify_session()
        if not info:
            # Distinguish a transient transport failure (server unreachable) from
            # a real auth rejection: verify_session returns the localized
            # "server unreachable" message ONLY on a transport error (a 401
            # clears the JWT). This keeps a still-authenticated user with a brief
            # network drop from being shown a logged-out login form.
            offline = bool(err) and err == t("st_server_unreachable")
            return {"authenticated": False, "offline": offline, "quota": None}
        self._last_quota = info
        # Per-account beta (Qwen) eligibility rides on the verify snapshot.
        self._beta_flag = bool(info.get("beta"))
        # Activation funnel: the app is up AND authenticated. Fire once per process.
        if not self._launch_reported:
            self._launch_reported = True
            voxis_client.report_event_async("app_launched")
        # Warm the session key in the background so the first Start after
        # opening the app skips the issuance round-trip.
        self._prefetch_session_key()
        return {"authenticated": True, "quota": info}

    def win_resize(self, width, height, anchor="br") -> bool:
        """Resize the frameless main window from the custom JS edge/corner grips
        (pywebview 6.2.1 has no native frameless resize). `anchor` names the edge
        or corner being dragged; the opposite corner is held fixed via FixPoint so
        left/top drags move the window correctly. Clamped to the min (940x600).
        No-op while maximized so an edge drag can't produce a half-maximized window."""
        if self._maximized:
            return False
        try:
            w = max(int(width), 940)
            h = max(int(height), 600)
            if self._main_window is None:
                return False
            fp = self._fixpoint(anchor)
            if fp is not None:
                self._main_window.resize(w, h, fp)
            else:
                self._main_window.resize(w, h)
            return True
        except Exception:
            pass
        return False

    def win_begin_drag(self, button=1, x_root=0, y_root=0, client_x=None, client_y=None) -> bool:
        """Hand the frameless-window drag off to the X11 window manager's own
        interactive move, triggered once on mousedown in index.html's
        `.pywebview-drag-region` (topbar/auth-titlebar).

        Two things were tried and rejected before this on Linux: (1)
        pywebview's own GTK `easy_drag` binds button-press/motion to the
        WHOLE webview with no concept of `-webkit-app-region: no-drag`, so it
        fought every button, slider and the custom resize grips for the same
        mouse events -- the window lurched instead of following the cursor.
        (2) A JS-driven drag polling `gtk_window_move()` every frame (this
        app's own `win_resize` pattern, reused for move) LOOKED right --
        smooth, monotonic (x,y) targets reached this method every ~16ms -- but
        the live window position diverged from every target sent, worst on
        the X axis (GTK's own docs: window managers are free to ignore
        gtk_window_move() on an already-mapped/shown window, or honor it only
        partially -- exactly this). `begin_move_drag` hands the ENTIRE
        gesture to Mutter's native `_NET_WM_MOVERESIZE`, which is the only
        path that actually respects real screen/multi-monitor edges and
        doesn't fight anything else. No-op while maximized, matching
        win_resize. Runs on GTK's own main loop via GLib.idle_add -- pywebview
        dispatches js_api calls off that thread, and GTK/GDK calls are only
        safe from the main loop."""
        if self._maximized or self._main_window is None:
            return False
        try:
            # PyGObject is a system package (not pip-installable), so it has no
            # stub available for static analysis; only reachable at runtime on
            # Linux, where it is genuinely present.
            from gi.repository import GLib as glib  # pyright: ignore[reportMissingImports]
            from webview.platforms.gtk import BrowserView
            win = self._main_window
            uid = win.uid
            log = logging.getLogger("voxis")
            log.warning("DIAG win_begin_drag called: button=%r x_root=%r y_root=%r "
                        "client_x=%r client_y=%r actual_win_pos=%r", button, x_root, y_root,
                        client_x, client_y, (win.x, win.y))

            def _begin():
                inst = BrowserView.instances.get(uid)
                if inst is None:
                    log.warning("DIAG win_begin_drag: no BrowserView instance for uid")
                    return
                try:
                    inst.window.begin_move_drag(int(button), int(x_root), int(y_root), 0)
                    log.warning("DIAG win_begin_drag: begin_move_drag() called OK")
                except Exception:
                    log.exception("DIAG win_begin_drag: begin_move_drag() raised")

            glib.idle_add(_begin)
            return True
        except Exception:
            logging.getLogger("voxis").exception("DIAG win_begin_drag outer failed")
            return False

    @staticmethod
    def _fixpoint(anchor):
        try:
            from webview.window import FixPoint as F
        except Exception:
            return None
        N, S, E, W = F.NORTH, F.SOUTH, F.EAST, F.WEST
        return {
            "r": N | W, "b": N | W, "br": N | W,
            "l": N | E, "bl": N | E,
            "t": S | W, "tr": S | W,
            "tl": S | E,
        }.get(anchor, N | W)

    # ── Window geometry persistence (size/position/maximized) ────────────────
    @staticmethod
    def _work_area_size():
        """Primary-monitor work-area size (px), best-effort. Used to reject an
        OS-driven maximize (Win+Up / title-bar double-click) that fires `resized`
        before `maximized` — without ordering guarantees the full work-area size
        would otherwise be stored as the RESTORE geometry, sticking the window at
        screen size after un-maximize. Returns None on any failure.

        Linux/other: pywebview's `screens` API exposes no taskbar/panel-exclusion
        equivalent to Windows' work area, so the primary display's full size is
        used instead — an approximation, acceptable given the ±4px tolerance this
        feeds into (see `_on_win_resized`)."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                # SPI_GETWORKAREA = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    return rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                pass
            try:
                import ctypes
                # SM_CXMAXIMIZED = 61, SM_CYMAXIMIZED = 62
                return (ctypes.windll.user32.GetSystemMetrics(61),
                        ctypes.windll.user32.GetSystemMetrics(62))
            except Exception:
                return None
        try:
            screens = webview.screens
            if screens:
                return screens[0].width, screens[0].height
        except Exception:
            pass
        return None

    def _on_win_resized(self, *a):
        if len(a) >= 2 and not self._maximized and not self._minimized:
            w, h = int(a[0]), int(a[1])
            # Skip a resize matching the work area: an OS maximize whose `resized`
            # arrives before `maximized` must not pollute the restore geometry.
            wa = self._work_area_size()
            if wa is not None and abs(w - wa[0]) <= 4 and abs(h - wa[1]) <= 4:
                return
            self._win_geom["w"], self._win_geom["h"] = w, h

    def _on_win_moved(self, *a):
        if len(a) >= 2 and not self._maximized and not self._minimized:
            self._win_geom["x"], self._win_geom["y"] = int(a[0]), int(a[1])

    def _on_win_maximized(self, *a):
        self._maximized = True

    def _on_win_minimized(self, *a):
        # Windows reports a minimized window's position/size via a sentinel
        # (e.g. -32000,-32000) — without this guard that lands in _win_geom and
        # gets persisted on close as if it were real restore geometry.
        self._minimized = True

    def _on_win_restored(self, *a):
        self._maximized = False
        self._minimized = False

    def _on_win_closing(self, *a):
        try:
            g = dict(self._win_geom)
            g["max"] = bool(self._maximized)
            self.cfg["window"] = g
            self._save_cfg()
        except Exception:
            pass
        # pywebview only leaves its message loop once EVERY window is gone
        # (winforms on_close: Application.Exit() fires at instances == 0), so an
        # open overlay outlives the main window: webview.start() never returns,
        # the post-loop cleanup that stops the session never runs, and the app
        # keeps translating (and billing) into a headless overlay while holding
        # the single-instance mutex — "closed it, it won't reopen" (field report,
        # 2026-07-13). Tear the overlay down here, on the closing edge, so the
        # loop can actually end. Not via toggle_overlay(False): that persists
        # overlay_enabled=False and would silently lose the user's preference.
        self._destroy_overlay()
        # Belt and braces: the user asked to close, so the process MUST die. If
        # anything still pins the message loop (a window we failed to destroy, a
        # wedged WebView2 teardown), webview.start() never returns and _shutdown
        # is never reached — the exact zombie this bug produced. Nothing may
        # cancel the close past this point, so an unconditional bounded exit is
        # safe; the normal path beats the timer and this never fires.
        self._close_watchdog = threading.Timer(20.0, _shutdown, args=(self,))
        self._close_watchdog.daemon = True
        self._close_watchdog.name = "voxis-close-watchdog"
        self._close_watchdog.start()

    def _destroy_overlay(self):
        win, self._overlay_win = self._overlay_win, None
        if win is None:
            return
        try:
            win.destroy()
        except Exception:
            _log.debug("overlay destroy failed", exc_info=True)

    def open_url(self, url: str) -> bool:
        # Allowlist http/https/mailto only so a crafted bridge call can never
        # launch file:, javascript: or other handler schemes via the default
        # browser. mailto is safe (opens the mail client, executes nothing) and
        # carries the Beta-application prefilled email.
        import webbrowser
        from urllib.parse import urlparse
        try:
            parts = urlparse(url)
        except Exception:
            return False
        if parts.scheme not in ("http", "https", "mailto"):
            return False
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return True

    def voxis_login(self, email: str, password: str) -> dict:
        if not IS_OFFICIAL_RELEASE:
            return {"ok": False, "quota": None, "error": "Login is disabled in developer builds."}
        from . import voxis_client
        token, err = voxis_client.pb_login(email, password)
        if not token:
            return {"ok": False, "quota": None, "error": err or "Login failed."}
        self._user_id = voxis_client.user_id_from_jwt()
        info, verr = voxis_client.verify_session()
        if not info:
            # Credentials are valid but the server rejected session verification
            # (no active license, quota exceeded, etc.). Clear the JWT so the
            # user is not left in a half-authenticated state, and surface the
            # actual server reason instead of a generic "login failed" string.
            voxis_client.clear_jwt()
            return {"ok": False, "quota": None, "error": verr or t("err_start_failed")}
        self._last_quota = info
        self._prefetch_session_key()
        return {"ok": True, "quota": info, "error": None}

    def google_login(self) -> dict:
        """Browser-relay Google/email sign-in (D1). Google blocks OAuth inside
        embedded webviews, and passwordless Google users have no password for
        /auth/login — so the sign-in runs in the SYSTEM browser on
        voxislive.com/app-login (PocketBase mints the token natively), and that
        page relays the PB token back to a single-use 127.0.0.1 listener guarded
        by a random nonce. No new Google Cloud config; reuses the live web flow."""
        if not IS_OFFICIAL_RELEASE:
            return {"ok": False, "quota": None, "error": "Login is disabled in developer builds."}
        import http.server
        import json as _json
        import secrets
        import webbrowser
        from urllib.parse import quote

        nonce = secrets.token_urlsafe(24)
        captured: dict = {}
        done = threading.Event()

        class _Handler(http.server.BaseHTTPRequestHandler):
            def _cors(self):
                origin = self.headers.get("Origin", "")
                if origin == "https://voxislive.com":
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                # Chrome/Edge Private Network Access: a public HTTPS page fetching
                # a loopback address gets a preflight that must be answered with
                # this header or the POST is blocked.
                self.send_header("Access-Control-Allow-Private-Network", "true")
                # This server's only payload is a one-time auth token; never let
                # it sit in a disk cache after the tab closes.
                self.send_header("Cache-Control", "no-store")

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                # Redirect fallback: if the page's fetch(POST) is blocked (CORS /
                # Private-Network-Access), app-login navigates here with the token
                # in the query instead. Same nonce gate.
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                token = (q.get("token") or [""])[0]
                ok = bool(token) and (q.get("nonce") or [""])[0] == nonce
                if ok and "token" not in captured:
                    captured["token"] = token
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<!doctype html><meta charset=utf-8><title>Voxis</title>"
                    b"<body style=\"font-family:Segoe UI,system-ui,sans-serif;background:#050507;"
                    b"color:#fafafa;display:flex;min-height:100vh;align-items:center;justify-content:center\">"
                    b"<div style=\"text-align:center\"><h2>Signed in</h2>"
                    b"<p style=\"color:#a1a1aa\">You can close this tab and return to Voxis.</p></div>"
                    # The token rode the query string (POST-first, this is only the
                    # fallback) — scrub it from the address bar and this tab's current
                    # history entry the instant the page loads, so it stops showing up
                    # in autocomplete/session-restore for a token that has already been
                    # consumed. Does not purge entries a browser already synced.
                    b"<script>history.replaceState(null,'',location.pathname)</script>")
                if ok:
                    done.set()

            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    body = self.rfile.read(length) if length else b""
                    data = _json.loads(body.decode("utf-8") or "{}")
                except Exception:
                    data = {}
                token = data.get("token") if isinstance(data, dict) else None
                ok = bool(token) and data.get("nonce") == nonce
                if ok and "token" not in captured:
                    captured["token"] = token
                self.send_response(200 if ok else 400)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}' if ok else b'{"ok":false}')
                if ok:
                    done.set()

            def log_message(self, format, *args):  # silence default stderr access log
                pass

        from . import voxis_client
        try:
            httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        except OSError as exc:
            voxis_client._log_detail("google_login bind", exc)
            return {"ok": False, "quota": None, "error": t("err_start_failed")}
        port = httpd.server_address[1]
        srv = threading.Thread(target=httpd.serve_forever, daemon=True)
        srv.start()

        url = f"https://voxislive.com/app-login?port={port}&nonce={quote(nonce)}"
        try:
            webbrowser.open(url)
        except Exception:
            pass

        done.wait(timeout=300)
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass

        token = captured.get("token")
        if not token:
            return {"ok": False, "quota": None, "error": t("auth_browser_timeout")}

        voxis_client.set_jwt(token)
        self._user_id = voxis_client.user_id_from_jwt()
        info, verr = voxis_client.verify_session()
        if not info:
            voxis_client.clear_jwt()
            return {"ok": False, "quota": None, "error": verr or t("err_start_failed")}
        self._last_quota = info
        self._beta_flag = bool(info.get("beta"))
        self._prefetch_session_key()
        return {"ok": True, "quota": info, "error": None}

    def voxis_quota(self) -> dict | None:
        if not IS_OFFICIAL_RELEASE:
            return None
        from . import voxis_client
        q = voxis_client.get_quota()
        if q:
            self._last_quota = q
        return q

    def voxis_logout(self) -> bool:
        from . import voxis_client
        voxis_client.clear_jwt()
        self._user_id = None
        return True

    def capture_hotkey(self, action):
        """Block on the next key combo, then bind it to `action`.

        Bounded by a watchdog and an explicit cancel_hotkey() so a recording
        box that never receives a keypress cannot hang the bridge thread. The
        captured combo is validated (non-empty, not already bound to another
        action) before it is persisted."""
        try:
            import keyboard
        except Exception:
            return None

        result: dict = {}
        done = threading.Event()
        self._hotkey_cancel = False

        def worker():
            try:
                result["combo"] = keyboard.read_hotkey(suppress=False)
            except Exception:
                result["combo"] = None
            finally:
                done.set()

        threading.Thread(target=worker, daemon=True).start()
        if not done.wait(HOTKEY_CAPTURE_TIMEOUT):
            # read_hotkey is blocking; nudge it with a synthetic keypress so the
            # worker returns instead of leaking a stuck thread on timeout.
            self._hotkey_cancel = True
            try:
                keyboard.press_and_release("esc")
            except Exception:
                pass
            done.wait(1.0)

        combo = result.get("combo")
        if self._hotkey_cancel or not combo:
            return None
        hk = self.cfg.setdefault("hotkeys", {})
        # Reject a combo already bound to a different action — duplicate bindings
        # would make _register_hotkeys' last writer silently win.
        if any(combo == c for a, c in hk.items() if a != action):
            self._emit_status(t("err_hotkey_duplicate"), "error")
            return None
        hk[action] = combo
        self._save_cfg()
        self._register_hotkeys()
        return combo

    def cancel_hotkey(self) -> bool:
        """Abort an in-flight capture_hotkey() (UI closed the recording box)."""
        self._hotkey_cancel = True
        try:
            import keyboard
            keyboard.press_and_release("esc")
        except Exception:
            pass
        return True

    def start(self, mode, consented=False):
        # consented=True means the UI consent modal was just accepted for THIS
        # start (the user may decline "don't show again", so it is not persisted).
        threading.Thread(target=self._start_thread, args=(mode, bool(consented)),
                         daemon=True).start()
        return True

    def _start_thread(self, mode, consented):
        # Endpoint switching calls win_audio._ensure_com, which CoInitializes this
        # short-lived session thread. Pair it with shutdown_com on the same thread
        # so the COM apartment is released and the thread id never lingers in
        # win_audio's per-thread bookkeeping (a later reused tid would otherwise
        # skip init and fault on CO_E_NOTINITIALIZED). No-op if we never owned it.
        # Windows-only module (imports comtypes at top) -- guarded the same way
        # pipeline.py gates endpoint switching, so this thread doesn't crash on
        # every start on a platform with no COM apartment to release at all
        # (caught on a real Raspberry Pi 5, 2026-07-19: the crash here was
        # masking whatever _start() itself raised, since an exception from the
        # finally block replaces one already propagating from the try).
        try:
            self._start(mode, consented)
        finally:
            if sysaudio.supports_endpoints():
                from . import win_audio
                win_audio.shutdown_com()

    def _consent_ok(self, mode, consented=False) -> bool:
        """Defense-in-depth consent gate. The primary consent modal lives in the
        UI; this backstop guarantees a path that never renders the modal (e.g. a
        hotkey) cannot launch meeting mode — which streams the other party's
        audio to a third party — before consent is given. Passes when consent was
        just acknowledged for this start OR was persisted via 'don't show again'."""
        if mode == "meeting" and not consented and not self.cfg.get("meeting_consent_ack"):
            self._emit_status(t("err_consent_required"), "error")
            return False
        return True

    def _cable_ok(self, mode) -> bool:
        """Defense-in-depth virtual-cable gate. Meeting mode streams the user's
        translated voice into a virtual microphone (VB-CABLE); with no cable
        installed there is nowhere to route it. The UI checks this before start,
        but the hotkey path never renders that prompt, so backstop it here.
        Only a clean None result (no cable found) blocks — a detection fault is
        allowed through so a transient COM error never hard-blocks a user who
        actually has a cable."""
        if mode != "meeting":
            return True
        try:
            available = detect_virtual_cable() is not None
        except Exception:
            return True
        if not available:
            self._emit_status(t("err_cable_required"), "error")
            return False
        return True

    def _prefetch_session_key(self):
        """Warm the session-key cache for the current incoming target (official
        build only). Fire-and-forget on a daemon thread: any error just leaves
        the cache cold and the next session start does its normal synchronous
        fetch. The beta (Qwen) resolver never reads this cache."""
        if not IS_OFFICIAL_RELEASE:
            return
        target = self.cfg.get("target_language_incoming", "")
        if not target:
            return

        with self._key_cache_lock:
            epoch = self._key_epoch

        def work():
            try:
                from . import voxis_client
                key, engine, model, quality, quota, workspace, key_type, fallback, _err = voxis_client.get_session_key(
                    target=target, caps=voxis_client.SESSION_KEY_CAPS)
                # Never cache an ephemeral token: its new-session window (2 min)
                # is shorter than KEY_PREFETCH_TTL, and a dead single-use token
                # at session start fails the first connect TERMINALLY instead of
                # retrying. The prefetch still warms TLS + the server-side token
                # cache, so the synchronous start fetch stays cheap.
                if key and key_type != "ephemeral":
                    with self._key_cache_lock:
                        # Only publish if the quota has not been exhausted while we
                        # were in flight. Otherwise this grant — issued when the
                        # user still had Pro minutes — would resurrect the paid
                        # engine for a spent free account.
                        if self._key_epoch == epoch:
                            self._key_cache[target] = (time.time(), engine, key,
                                                       model, quality, workspace,
                                                       fallback)
                if isinstance(quota, dict):
                    self._last_quota = quota
                    # Trial-only field, piggybacked on the quota dict the same
                    # way cascade_daily_minutes is (voxis_client.py) rather
                    # than widening the already-awkward 9-tuple return.
                    self.cfg["_cascade_voice_tier"] = quota.get(
                        "cascade_voice_tier", "standard")
            except Exception:
                pass  # cold cache == old behavior

        threading.Thread(target=work, daemon=True,
                         name="voxis-key-prefetch").start()

    def _pop_prefetched_key(self, target):
        """Single-use cache take — ephemeral tokens are not reused across
        sessions. Returns (engine, key, model, quality, workspace, fallback) or
        None (stale/miss).

        A grant is only as good as the quota it was issued under. The epoch guard
        in the prefetch stops the common race, but a grant can also simply go stale
        in the cache (TTL is 4 min) while the last minutes burn away. So the free/
        paid boundary is re-checked HERE, at the moment of use: a spent taste never
        starts a voiced session, whatever the cache holds. Belt to the epoch's
        braces — this is the invariant the server cannot enforce for us, because it
        never sees a start that reuses a grant it issued minutes ago."""
        with self._key_cache_lock:
            hit = self._key_cache.pop(target, None)
        if not hit or time.time() - hit[0] >= KEY_PREFETCH_TTL:
            return None
        engine = hit[1]
        if engine != ENGINE_CASCADE and self._taste_spent():
            # Out of Pro minutes, holding a Pro grant: drop it and let the start do
            # its synchronous fetch, which the server answers with the cascade.
            return None
        return hit[1:]

    def _taste_spent(self) -> bool:
        """True when the license has no billable minutes left. Fails OPEN (False)
        on an unknown quota: refusing a paid grant we are unsure about would break
        a paying customer, while wrongly allowing one costs at most one session
        that the server's own 402 stops within a heartbeat."""
        q = self._last_quota
        if not isinstance(q, dict) or q.get("unlimited"):
            return False
        rem = q.get("remaining")
        if rem is None:
            allowed, used = q.get("allowed_minutes"), q.get("used_minutes")
            if allowed is None or used is None:
                return False
            rem = allowed - used
        try:
            return float(rem) <= 0
        except (TypeError, ValueError):
            return False

    def _apply_qwen_workspace(self, engine, workspace):
        """Adopt the server-issued DashScope workspace id (workspace-scoped
        sk-ws-… keys need it for the MAAS WS host — see make_translator).
        Server-controlled so a workspace change never needs a client release."""
        if engine == "qwen" and workspace:
            self.cfg["qwen_workspace"] = str(workspace)

    def _build_engine_resolver(self):
        """Returns resolve(target) -> (engine, key, model, fallback), called once
        per pipeline. `fallback` is a {key, model, workspace} dict for a sibling
        Qwen pool (see voxis_client.get_session_key) or None for every other
        engine/path — fed to engines.make_translator so a pool-specific terminal
        error gets one fast retry on a different pool before an on_fatal swap to
        Gemini (base_translator.py).

        SaaS asks the server, which routes by TARGET language and can fail over to
        Gemini (the engine selector is server-controlled). Dev/BYOK routes locally
        over the stored keys. Raises a localized error if no key is available.
        """
        from .config import ENGINE_CASCADE, ENGINE_GEMINI, qwen_can_voice, resolve_model
        # Beta engine opt-in (Qwen): only honored when the account is
        # beta-eligible (server flag; dev builds are always eligible) AND the
        # user switched it on. Never touches the normal server-side routing.
        beta_qwen = (self._beta_allowed()
                     and bool((self.cfg.get("beta") or {}).get("enabled")))
        if not IS_OFFICIAL_RELEASE:
            # OSS/BYOK is Gemini-only.
            from . import byok_store
            from .config import ENGINE_GEMINI, ENGINE_QWEN
            uid = self._ensure_user_id()
            keys = byok_store.load_byok(uid) if uid else {}
            # Dev beta path: a DashScope key in config.json ("qwen_key") selects
            # the Qwen engine locally — sandbox-style, no server round-trip.
            if beta_qwen and self.cfg.get("qwen_key"):
                gem = keys.get("gemini")
                def _resolve_byok_beta(target, force_gemini=False):
                    # Qwen has no VOICE for some targets (text-only tier) — those
                    # would give subtitles with no audio, so prefer Gemini when a
                    # key is available. force_gemini is the mid-session failover
                    # (see IncomingPipeline._failover_to_gemini).
                    if gem and (force_gemini or not qwen_can_voice(self.cfg, target)):
                        if not force_gemini:
                            _log.info("Qwen beta has no voice for target %r; using Gemini", target)
                        return ENGINE_GEMINI, gem, resolve_model(self.cfg, ENGINE_GEMINI), None
                    if force_gemini:
                        raise RuntimeError(t("st_no_key_offline"))
                    # BYOK/dev has no server-side pool concept — fallback is
                    # always None; a dead key here is a local config problem,
                    # not a pool-capacity blip worth retrying on a sibling pool.
                    return (ENGINE_QWEN, self.cfg.get("qwen_key"),
                            resolve_model(self.cfg, ENGINE_QWEN), None)
                # Genuine beta session → let Qwen honor cfg["beta"]["clone"].
                # Read via getattr(resolve, "beta_active", False) by the caller
                # (pipeline.py) — an ad-hoc attribute on the closure, not a
                # statically-typed callable shape; see the resolve builder's
                # docstring for why (four differently-shaped resolvers here).
                _resolve_byok_beta.beta_active = True  # pyright: ignore[reportFunctionMemberAccess]
                return _resolve_byok_beta
            if not keys.get("gemini"):
                raise RuntimeError(t("st_no_key_offline"))

            def _resolve_byok(target, force_gemini=False):
                return ENGINE_GEMINI, keys.get("gemini"), resolve_model(self.cfg, ENGINE_GEMINI), None
            return _resolve_byok

        from . import voxis_client

        # Mid-session failover (IncomingPipeline._failover_to_gemini): a routed
        # engine that gave up — a spent DashScope balance reports as a terminal
        # 'arrearage' — needs a Gemini key NOW. Calling /auth/session-key with no
        # ?caps is the server's backward-compat path and always answers with the
        # plain Gemini key (session_key.go defaults engine to "gemini" when the
        # client is not routing-aware), so no server change is needed.
        def gemini_key():
            key, _engine, model, quality, quota, _ws, _kt, _fb, err = voxis_client.get_session_key()
            if not key:
                raise RuntimeError(err or t("st_no_key"))
            if isinstance(quota, dict):
                self._last_quota = quota
            if quality:
                self.cfg["quality_preset"] = quality
            # Gemini has no sibling-pool concept — fallback is always None here.
            return ENGINE_GEMINI, key, (model or resolve_model(self.cfg, ENGINE_GEMINI)), None

        # Gemini key fountain for LiveTranslator: called on the translator's
        # thread before every reconnect once its single-use ephemeral token has
        # been spent (a raw-key session never calls it). No target → the server
        # always answers Gemini (an empty target routes to the catch-all), and
        # because ephemeral tokens are uses:1 this re-runs the quota + device
        # gates on every 13-min rotation — the point of Tier A5. Raising here
        # just fails that reconnect attempt; the translator retries with backoff.
        def gemini_key_provider():
            key, _engine, _model, _quality, quota, _ws, _kt, _fb, err = \
                voxis_client.get_session_key(caps=voxis_client.SESSION_KEY_CAPS)
            if not key:
                raise RuntimeError(err or t("st_no_key"))
            if isinstance(quota, dict):
                self._last_quota = quota
            return key

        if beta_qwen:
            # SaaS beta: ask the server for the Qwen session key explicitly. The
            # server re-checks the account's beta flag (client is not trusted)
            # and refuses otherwise — then we fall through to normal routing.
            def _resolve_saas_beta(target, force_gemini=False):
                err = None
                if force_gemini:
                    return gemini_key()
                # Skip Qwen entirely for a target it can't voice (text-only tier):
                # the standard engine gives translated speech, not just subtitles.
                if qwen_can_voice(self.cfg, target):
                    key, engine, model, quality, quota, workspace, _kt, fallback, err = voxis_client.get_session_key(
                        target=target, caps=voxis_client.SESSION_KEY_CAPS, engine="qwen")
                    if key and engine == "qwen":
                        if isinstance(quota, dict):
                            self._last_quota = quota
                        self._apply_qwen_workspace(engine, workspace)
                        return engine, key, (model or resolve_model(self.cfg, engine)), fallback
                else:
                    _log.info("Qwen beta has no voice for target %r; using standard routing", target)
                key, engine, model, quality, quota, workspace, _kt, fallback, err2 = voxis_client.get_session_key(
                    target=target, caps=voxis_client.SESSION_KEY_CAPS,
                    mode=getattr(self, "_starting_mode", None))
                if key:
                    if isinstance(quota, dict):
                        self._last_quota = quota
                    if quality:
                        self.cfg["quality_preset"] = quality
                    self._apply_qwen_workspace(engine, workspace)
                    return engine, key, (model or resolve_model(self.cfg, engine)), fallback
                raise RuntimeError(err or err2 or t("st_no_key"))
            # Both read via getattr(resolve, "...", default) by the caller — see
            # the docstring note on _resolve_byok_beta.beta_active above.
            _resolve_saas_beta.gemini_key_provider = gemini_key_provider  # pyright: ignore[reportFunctionMemberAccess]
            _resolve_saas_beta.beta_active = True  # pyright: ignore[reportFunctionMemberAccess]
            return _resolve_saas_beta

        # Single-round-trip start: /auth/session-key now verifies the token
        # inline on a cold server cache and returns the quota snapshot alongside
        # the key, so the old verify → quota → session-key sequence (3 RTTs on a
        # slow link) collapses into this one call. Auth/quota/license failures
        # surface as localized errors from get_session_key itself.
        # Zero-round-trip start: a fresh prefetched key (warmed at login /
        # target change / previous stop) skips even that one call.
        def _resolve_saas(target, force_gemini=False, cascade_rescue=False, reason=None):
            if force_gemini:
                return gemini_key()
            if cascade_rescue:
                # Server-authoritative grant (see voxis_client.get_session_key's
                # rescue= docstring): a falsy key here just means "not granted
                # right now" — not_paid/not_taste/meeting/qwen-is-fine are all
                # legitimate reasons and none of them are errors. The caller
                # (pipeline._swap_to_cascade) treats a non-cascade/no-key
                # response as "no rescue" and lets the existing give-up path
                # surface normally. `reason="watchdog"` (client-confirmed dead
                # stream, see pipeline._swap_to_cascade) lets the server grant
                # this independently of the fleet-storm window, rate-limited
                # server-side instead.
                key, engine, model, quality, _quota, workspace, _kt, _fb, _err = voxis_client.get_session_key(
                    target=target, caps=voxis_client.SESSION_KEY_CAPS,
                    mode=getattr(self, "_starting_mode", None), rescue=True,
                    reason=reason)
                if key and engine == ENGINE_CASCADE:
                    if quality:
                        self.cfg["quality_preset"] = quality
                    return engine, key, (model or resolve_model(self.cfg, engine)), None
                return None, None, None, None
            pre = self._pop_prefetched_key(target)
            if pre:
                engine, key, model, quality, workspace, fallback = pre
                if quality:
                    self.cfg["quality_preset"] = quality
                # No quota on the prefetch-hit path — best-effort from the last
                # live fetch (same staleness tolerance the epoch guard above
                # already accepts for this cache).
                if isinstance(self._last_quota, dict):
                    self.cfg["_cascade_voice_tier"] = self._last_quota.get(
                        "cascade_voice_tier", "standard")
                self._apply_qwen_workspace(engine, workspace)
                return engine, key, (model or resolve_model(self.cfg, engine)), fallback
            key, engine, model, quality, quota, workspace, _kt, fallback, err = voxis_client.get_session_key(
                target=target, caps=voxis_client.SESSION_KEY_CAPS,
                mode=getattr(self, "_starting_mode", None))
            if key:
                if isinstance(quota, dict):
                    self._last_quota = quota  # keeps the paid-badge gate fresh
                    self.cfg["_cascade_voice_tier"] = quota.get(
                        "cascade_voice_tier", "standard")
                if quality:
                    self.cfg["quality_preset"] = quality  # server-controlled default
                self._apply_qwen_workspace(engine, workspace)
                return engine, key, (model or resolve_model(self.cfg, engine)), fallback
            # Routed engine unavailable (503) → fall back to Gemini via the legacy
            # path. PAID ONLY (2026-08-12 cost-pressure policy — see
            # .vault/decision-log.md): the legacy no-caps call always answers
            # Gemini regardless of tier, so without this gate a free/taste
            # session would silently buy a Gemini session the moment Qwen is
            # unavailable — exactly the leak measured in usage_events during
            # the 2026-08-06..09 qwen_enabled=false window. The server now
            # also refuses this 503 itself for free tier (session_key.go), so
            # this is defense-in-depth, not the only gate.
            if self._is_paid():
                key, engine, model, quality, quota, workspace, _kt, _fb, err2 = voxis_client.get_session_key()
                if key:
                    if quality:
                        self.cfg["quality_preset"] = quality
                    return "gemini", key, (model or resolve_model(self.cfg, "gemini")), None
                raise RuntimeError(err or err2 or t("st_no_key"))
            raise RuntimeError(err or t("st_no_key"))
        # Read via getattr(resolve, "gemini_key_provider", None) by the caller —
        # see the docstring note on _resolve_byok_beta.beta_active above.
        _resolve_saas.gemini_key_provider = gemini_key_provider  # pyright: ignore[reportFunctionMemberAccess]
        return _resolve_saas

    def _start(self, mode, consented=False):
        # Single-flight: serialize the whole transition so a rapid start→stop or
        # a burst of set_cfg restarts can never run two _start bodies against one
        # controller. start() is thereby idempotent for the active mode.
        with self._lifecycle:
            if not self._consent_ok(mode, consented):
                return
            if not self._cable_ok(mode):
                return
            # The key resolvers run per pipeline and only know the TARGET; the
            # server needs the mode too, because it refuses to cascade a meeting
            # (the other party would hear a synthetic voice speaking as the user).
            self._starting_mode = mode
            # A running sound-check probe must not coexist with the session's
            # own capture — release it before the pipeline opens its stream.
            self.soundcheck_stop()
            self._badge = (t("badge_connecting"), "#fbbf24", "warn")
            from . import voxis_client
            try:
                # Per-target engine+key+model resolver (SaaS=server-routed,
                # dev=local). Built once; each pipeline calls it for its target.
                self.controller.resolve = self._build_engine_resolver()
                # Fresh session: drop the previous stop's auto-saved file so a
                # post-stop Save on the NEW session can't re-surface a stale one.
                self._last_saved_file = None
                self._session_error = False
                # Decide this session's self-contained output folder up front (from
                # the wall-clock start) so the recorder's WAVs and the transcript
                # JSON saved on stop share one folder + stamp. The folder itself is
                # created lazily on first write (recorder / save_txt), so a blocked
                # Documents dir can't fail the start here.
                t0 = time.time()
                self._session_dirname = transcript_store.session_dir_name(t0)
                self._session_dir = os.path.join(self._transcript_dir(),
                                                 self._session_dirname)
                # Anchor the transcript timeline to the SESSION, not to the first
                # translated token. Capture (and the WAV recorder) start here, so
                # turn offsets — and therefore every exported cue — line up with
                # the recording; anchoring on first output silently shifted them
                # by however long the room stayed quiet (7m46s in one field
                # session). Sharing t0 with the folder stamp also keeps the JSON's
                # `started` equal to the folder name it sits in. Set BEFORE start()
                # so the engine's own connect/reconnect events can be timestamped.
                with self._text_lock:
                    self._session_start = t0
                try:
                    started = self.controller.start(mode, session_dir=self._session_dir,
                                                    paid=self._is_paid(),
                                                    taste_rescue=self._taste_active())
                except BaseException:
                    with self._text_lock:
                        self._session_start = 0.0
                    raise
                if started is False:
                    with self._text_lock:
                        self._session_start = 0.0
                        self._session_events = []
                    self._badge = (t("badge_idle"), "#8593a6", "")
                    return
                self._badge = (t("badge_active", mode=self._mode_name(mode)), "#34d399", "on")
            except voxis_client.DeviceBlockedError as e:
                # This machine's free tier belongs to a different account (Tier
                # A3b block) — not a spent quota. Not an error/exception in the
                # product sense, so no error badge and no _session_error (that
                # flag suppresses the rating prompt, which a device mismatch has
                # nothing to do with). The status line always shows; the richer
                # "switch account" card only when the server actually resolved
                # the other account (older servers, or a lookup miss, send the
                # flag alone — fall back to the plain status line for those).
                self._badge = (t("badge_idle"), "#8593a6", "")
                self._emit_status(str(e), "warn")
                if e.first_account:
                    self._put_event(("device_blocked", {
                        "first_account": e.first_account,
                        "remaining_minutes": e.remaining_minutes,
                    }))
            except Exception as e:
                # Log the raw exception; surface a localized message to the UI
                # rather than forwarding str(e) (which may be an English/library
                # string) into the user-facing transcript.
                _log.exception("session start failed (mode=%s)", mode)
                self._emit_status(self._start_error_message(e), "error")

    def _start_error_message(self, exc) -> str:
        """Map a start failure to a localized, user-actionable message. A
        RuntimeError we raised already carries a localized string. A ValueError
        comes from device resolution (audio_io.find_device / the CABLE feedback
        guard in pipeline.py) — actionable in English but not localized, so map
        it to a generic "check your audio device setup" line instead of losing
        the signal in the fully generic fallback. Anything else is an
        unexpected fault and gets that generic localized line."""
        if isinstance(exc, RuntimeError) and str(exc):
            return str(exc)
        if isinstance(exc, ValueError) and str(exc):
            return t("err_device_config")
        return t("err_start_failed")

    # A session earns the rating ask only if Voxis actually did the job: it
    # produced translation, ran long enough to be more than a poke, and nothing
    # failed. Asking right after a crash is how an app collects one-star ratings.
    REVIEW_MIN_SECONDS = 120.0
    REVIEW_AFTER_SESSIONS = 3

    def _note_good_session(self):
        """Count a clean session and, on the third, raise the rating prompt once.

        Called from _stop while the session's own state is still intact. Never
        raises — a bookkeeping failure must not break the teardown path."""
        try:
            if self._session_error or not self._session_start:
                return
            if time.time() - self._session_start < self.REVIEW_MIN_SECONDS:
                return
            if self.cfg.get("review_prompted") or not store_review.available():
                return
            n = int(self.cfg.get("good_sessions", 0) or 0) + 1
            self.cfg["good_sessions"] = n
            if n >= self.REVIEW_AFTER_SESSIONS:
                # Marked before the prompt is shown, not after it is answered: a
                # card dismissed by closing the window must not come back.
                self.cfg["review_prompted"] = True
                self._put_event(("review", None))
            save_config(self.cfg)
        except Exception:
            logging.getLogger("voxis").debug("review prompt bookkeeping failed",
                                             exc_info=True)

    def rate_voxis(self):
        """Open the Store's own rating sheet. Nothing is offered in return — see
        store_review for why that matters."""
        return store_review.open_review_page()

    # ---------- the inverse demo (free-voice preview) ----------
    def free_voice_preview(self):
        """Speak the line the user just heard in the FREE tier's voice, then hand
        the paid voice straight back. See free_preview for why the comparison has
        to happen HERE — mid-taste, reversible — and not at the wall.

        Returns immediately: the first call may download a ~60 MB voice, which
        must not block the UI thread. Progress arrives as ('preview', {...})
        events; JS localizes the `code`, so no string crosses this boundary."""
        with self._preview_lock:
            if self._preview_busy:
                return {"ok": False, "code": "busy"}
            self._preview_busy = True
        threading.Thread(target=self._preview_thread, daemon=True).start()
        return {"ok": True}

    def _preview_thread(self):
        try:
            from . import free_preview
            with self._text_lock:
                line = self._last_line
            if not line.strip():
                logging.getLogger("voxis").info("free-voice preview: no line to replay")
                self._preview_event("error", "no_line")
                return
            lang = self.cfg.get("target_language_incoming") or "en"
            if not free_preview.voice_available(lang):
                # Not a failure — the honest shape of the free tier in this
                # language. Saying so is worth more than hiding the button.
                self._preview_event("error", "no_voice")
                return
            self._preview_event("loading", None)
            pcm = free_preview.synth_pcm16(lang, line)
            self._play_clip(pcm, "playing")
            self._preview_event("done", None)
        except Exception as exc:
            logging.getLogger("voxis").info("free-voice preview failed: %s", exc)
            self._preview_event("error", "failed")
        finally:
            with self._preview_lock:
                self._preview_busy = False

    def pro_voice_replay(self):
        """Replay the paid voice, so the two can be heard back to back. Offered
        after the free clip, when the contrast is freshest — the highest-intent
        moment of the whole taste."""
        with self._preview_lock:
            if self._preview_busy:
                return {"ok": False, "code": "busy"}
            self._preview_busy = True
        threading.Thread(target=self._pro_replay_thread, daemon=True).start()
        return {"ok": True}

    def _pro_replay_thread(self):
        try:
            pcm = self.controller.recent_pro_pcm()
            if not pcm:
                logging.getLogger("voxis").info("pro-voice replay: nothing buffered")
                self._preview_event("error", "no_pro")
                return
            self._play_clip(pcm, "playing_pro")
            self._preview_event("done", None)
        except Exception as exc:
            logging.getLogger("voxis").info("pro-voice replay failed: %s", exc)
            self._preview_event("error", "failed")
        finally:
            with self._preview_lock:
                self._preview_busy = False

    def _play_clip(self, pcm: bytes, state: str):
        """Play a demo clip wherever the user happens to be. During a session it
        borrows the live Player (and the paid voice stands down for the clip's
        length); afterwards it opens its own — the A/B card lives after the
        session, because that is when the user is actually looking at Voxis."""
        from . import free_preview

        secs = free_preview.duration_seconds(pcm)
        self._preview_event(state, None, seconds=round(secs, 1))
        pipe = self.controller.incoming()
        if pipe is not None:
            pipe.play_free_preview(pcm, secs)
            time.sleep(secs + 0.6)
        else:
            free_preview.play_standalone(self.cfg, pcm)

    def _preview_event(self, state, code, **extra):
        self._put_event(("preview", {"state": state, "code": code, **extra}))

    def mark_seen(self, key):
        """Persist a one-time UI beat (the ladder explainer, the contrast card) so
        it never asks twice. Whitelisted: JS must not be able to write arbitrary
        config keys through this door."""
        if key not in ("ladder_seen", "contrast_shown", "latency_note_seen"):
            return False
        self.cfg[key] = True
        return self._save_cfg()

    def stop(self):
        threading.Thread(target=self._stop_thread, daemon=True).start()
        return True

    def _stop_thread(self):
        # Endpoint restore runs on this stop thread and CoInitializes it via
        # win_audio._ensure_com; balance it with shutdown_com on the same thread.
        # Guarded the same way as _start_thread above -- see that comment.
        try:
            self._stop()
        finally:
            if sysaudio.supports_endpoints():
                from . import win_audio
                win_audio.shutdown_com()

    def _stop(self):
        # Idempotent: serialized against _start so a stop racing a start cannot
        # tear down a half-built session, and a redundant stop is a no-op.
        # Invalidate any pending _maybe_restart debounce timer FIRST: its run()
        # reads controller.mode outside the lock, and mid-teardown that still
        # says the old mode — without this bump the timer would resurrect the
        # session (capture + billing) the user just stopped.
        self._restart_token += 1
        with self._lifecycle:
            # Auto-save the session on stop so the transcript is never lost.
            # Saved silently here (avoids a status race with the teardown below);
            # the path + open/reveal actions are surfaced once, after teardown.
            saved = self.save_txt(silent=True)
            # Read the session's own state before the teardown below clears it.
            self._note_good_session()
            self.controller.stop()
            self._overlay_text = ""
            self._badge = (t("badge_idle"), "#8593a6", "")
            # New session starts fresh: clear the per-session timeline + buffers
            # so the next run does not append onto the stopped session's turns.
            # Guarded by _text_lock against any still-draining _on_text call.
            with self._text_lock:
                self._turns = []
                self._session_events = []
                self._src_track = []
                self._audio_track = []
                self._session_start = 0.0
                self._session_dir = None
                self._session_dirname = None
                self._session_file = None
                self._lines = []
                for st in self._legs.values():
                    st.reset()
                self._cur_spk = None
                self._spk_seen = set()
        # Tell the user where the auto-saved transcript went and offer open/reveal
        # actions, so pressing Stop confirms the save instead of leaving them to
        # click "Save transcript" and hit "nothing to save". Remember the path so
        # a post-stop Save button click can re-surface it (see save_txt).
        if isinstance(saved, dict) and saved.get("ok"):
            self._last_saved_file = saved["path"]
            self._emit_status(t("saved_to", path=saved["path"]))
            self._put_event(("saved", saved["file"]))
        # Re-warm the session key for the (likely same-target) next start — the
        # previous one was consumed by this session's resolver.
        self._prefetch_session_key()

    def toggle_overlay(self, on):
        self.cfg["overlay_enabled"] = bool(on)
        self._save_cfg()
        if on and self._overlay_win is None:
            try:
                w, sw, sh = 780, 1920, 1080
                try:
                    if sys.platform == "win32":
                        import ctypes
                        sw = ctypes.windll.user32.GetSystemMetrics(0)
                        sh = ctypes.windll.user32.GetSystemMetrics(1)
                    else:
                        screens = webview.screens
                        if screens:
                            sw, sh = screens[0].width, screens[0].height
                except Exception:
                    pass
                self._ov_w = w
                self._ov_x = (sw - w) // 2
                self._ov_bottom = int(sh * 0.86)
                self._overlay_win = webview.create_window(
                    "VoxisOverlay", html=_OVERLAY_HTML, frameless=True, on_top=True,
                    width=w, height=84, x=self._ov_x, y=self._ov_bottom - 84,
                    background_color="#0a0b10", js_api=OverlayJsApi(self), hidden=True,
                )
            except Exception:
                self._overlay_win = None
        elif not on:
            self._destroy_overlay()
        return True

    # ---------- virtual cable (meeting mode) ----------
    def meeting_cable_available(self) -> bool:
        """True when a virtual audio cable is installed, so the UI can block
        meeting mode (which routes the translated voice into a virtual mic)
        before start instead of failing mid-launch."""
        try:
            return detect_virtual_cable() is not None
        except Exception:
            return False

    def open_cable_download(self) -> bool:
        """Open the VB-CABLE download page so a user missing the virtual mic can
        install it. Disabled on the official build: Store policy 10.1.5 excludes
        an app from facilitating acquisition of a non-Microsoft driver, so the
        SaaS flavor only informs and the user installs VB-CABLE themselves.
        Returns False if disabled or no system browser could be launched."""
        if IS_OFFICIAL_RELEASE:
            return False
        try:
            import webbrowser
            return webbrowser.open("https://vb-audio.com/Cable/")
        except Exception:
            return False

    # ---------- onboarding tour (modal/JS lives in the web UI) ----------
    def mark_onboarding_done(self) -> bool:
        self.cfg["onboarding_done"] = True
        self._save_cfg()
        return True

    def reset_onboarding(self) -> bool:
        # Backs the "show tour again" link.
        self.cfg["onboarding_done"] = False
        self._save_cfg()
        return True

    # ---------- main-window controls (custom title bar) ----------
    def win_minimize(self):
        if self._main_window is None:
            return True
        try:
            self._main_window.minimize()
        except Exception:
            pass
        return True

    def win_toggle_max(self):
        # maximize()/restore() block until the native WindowState change lands,
        # which synchronously fires WinForms' Resize event — and that spawns a
        # thread that runs _on_win_maximized/_on_win_restored and mutates
        # self._maximized concurrently with this method. Re-reading
        # self._maximized AFTER the native call (the old `not self._maximized`)
        # raced that thread: if it won, this negated the value IT had just set,
        # flipping _maximized back to the wrong state (window visually restored,
        # flag stuck True forever — which also permanently no-ops win_resize).
        # Capturing the pre-call state up front and negating that instead makes
        # the outcome independent of the event thread's timing.
        if self._main_window is None:
            return True
        try:
            was_max = self._maximized
            if was_max:
                self._main_window.restore()
            else:
                self._main_window.maximize()
            self._maximized = not was_max
        except Exception:
            pass
        return True

    def win_close(self):
        if self._main_window is None:
            return True
        try:
            self._main_window.destroy()
        except Exception:
            pass
        return True

    def overlay_text(self):
        if time.time() > self._overlay_until:
            return ""
        # Local was named `t`, shadowing the module-level i18n t(); renamed so
        # this method can localize if ever needed.
        return _cap_subtitle(self._overlay_text)

    def overlay_badge(self):
        """Localized attribution text for the overlay footer, or "" when the badge
        is disabled. The overlay window is a separate pywebview document with its
        own JS scope (no access to the main window's I18N dict), so it pulls the
        localized string from here via window.pywebview.api.overlay_badge()."""
        if not self._show_badge():
            return ""
        return t("powered_by")

    def overlay_poll(self):
        """Single combined poll for the overlay window: caption + badge in one
        bridge round-trip (the overlay previously made two separate api calls
        every 150 ms tick — half the crossings for the same data)."""
        return {"text": self.overlay_text(), "badge": self.overlay_badge()}

    def overlay_fit(self, h):
        if self._overlay_win is None:
            return True
        try:
            # Upper clamp allows for the optional attribution footer row.
            h = max(64, min(300, int(h)))
            w = self._ov_w
            self._overlay_win.resize(w, h)
            self._overlay_win.move(self._ov_x, self._ov_bottom - h)
            self._round_overlay()
        except Exception:
            pass
        return True

    def _round_overlay(self):
        """Clips the overlay to a rounded rectangle region (no transparency).

        Windows-only (GDI region clip). Elsewhere the overlay simply keeps its
        rectangular shape — cosmetic, not functional."""
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        hwnd = u.FindWindowW(None, "VoxisOverlay")
        if not hwnd:
            return
        rect = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        pw, ph = rect.right - rect.left, rect.bottom - rect.top
        if pw <= 0 or ph <= 0:
            return
        radius = min(pw, ph, max(22, ph // 2))
        rgn = g.CreateRoundRectRgn(0, 0, pw + 1, ph + 1, radius, radius)
        u.SetWindowRgn(hwnd, rgn, True)

    def overlay_show(self):
        if self._overlay_win is not None:
            try:
                self._overlay_win.show()
                self._round_overlay()
            except Exception:
                pass
        return True

    def overlay_hide(self):
        if self._overlay_win is not None:
            try:
                self._overlay_win.hide()
            except Exception:
                pass
        return True

    # ---------- sound check (idle-only system + microphone level probes) ----------
    def soundcheck_start(self):
        """Start independent system-loopback and selected-microphone probes.

        Each probe only produces a peak level for the modal meters (poll's
        ``sc`` / ``sc_mic`` fields). A failure on one side does not hide a
        healthy device on the other. Refused while a session runs; auto-stops
        after 60 s so an abandoned modal cannot hold either capture forever.

        Goes through the sysaudio dispatch layer (not a direct
        process_loopback import) so this works on Linux too -- the direct
        import unconditionally pulled in comtypes at module load, crashing
        this probe on every Linux click (caught on a real VM test,
        2026-07-19). On Linux, make_process_loopback needs a routing handle
        (make_capture_routing sets up + tears down the same VoxisCapture
        routing a real session would use); Windows ignores it."""
        if self.controller.mode or self._sc is not None or self._sc_mic is not None:
            return {
                "ok": self._sc is not None or self._sc_mic is not None,
                "system_ok": self._sc is not None,
                "mic_ok": self._sc_mic is not None,
            }

        system_ok = False
        mic_ok = False

        def on_system_chunk(pcm):
            # ProcessExcludeLoopback/PipeWireCapture hand us float32 samples
            # already normalized to -1..1, not raw PCM16 bytes.
            try:
                peak = float(max(pcm.max(), -pcm.min(), 0.0)) if pcm.size else 0.0
            except Exception:
                return
            # Fast attack, slow decay so short transients stay visible a beat.
            self._sc_level = max(peak, self._sc_level * 0.85)

        try:
            self._sc_routing = sysaudio.make_capture_routing()
            self._sc = sysaudio.make_process_loopback(
                on_system_chunk, routing_handle=self._sc_routing)
            self._sc.start()
            system_ok = True
        except Exception:
            _log.exception("soundcheck: could not start system loopback probe")
            if self._sc is not None:
                try:
                    self._sc.stop()
                except Exception:
                    pass
            if self._sc_routing is not None:
                try:
                    sysaudio.teardown_capture_routing(self._sc_routing)
                except Exception:
                    pass
                self._sc_routing = None
            self._sc = None

        def on_mic_chunk(pcm):
            try:
                peak = float(max(pcm.max(), -pcm.min(), 0.0)) if pcm.size else 0.0
            except Exception:
                return
            self._sc_mic_level = max(peak, self._sc_mic_level * 0.85)

        try:
            mic_name = self.cfg.get("devices", {}).get("microphone", DEFAULT_DEVICE)
            mic_device = find_device(mic_name, "input")
            self._sc_mic = Capture(mic_device, on_mic_chunk)
            self._sc_mic.start()
            mic_ok = True
        except Exception:
            _log.exception("soundcheck: could not start microphone probe")
            if self._sc_mic is not None:
                try:
                    self._sc_mic.stop()
                except Exception:
                    pass
            self._sc_mic = None

        if system_ok or mic_ok:
            self._sc_timer = threading.Timer(60.0, self.soundcheck_stop)
            self._sc_timer.daemon = True
            self._sc_timer.start()
        return {"ok": system_ok or mic_ok, "system_ok": system_ok, "mic_ok": mic_ok}

    def soundcheck_stop(self):
        sc, self._sc = self._sc, None
        mic, self._sc_mic = self._sc_mic, None
        timer, self._sc_timer = self._sc_timer, None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        if sc is not None:
            try:
                sc.stop()
            except Exception:
                pass
        if mic is not None:
            try:
                mic.stop()
            except Exception:
                pass
        routing, self._sc_routing = self._sc_routing, None
        if routing is not None:
            try:
                sysaudio.teardown_capture_routing(routing)
            except Exception:
                pass
        self._sc_level = 0.0
        self._sc_mic_level = 0.0
        return True

    def soundcheck_play_tone(self):
        """Play a safe diagnostic tone through the selected translation output."""
        try:
            output_name = self.cfg.get("devices", {}).get(
                "headphones_output", DEFAULT_DEVICE)
            output_device = find_device(output_name, "output")
            play_test_tone(output_device)
            return {"ok": True}
        except Exception as exc:
            _log.exception("soundcheck: could not play output test tone")
            return {"ok": False, "error": str(exc)}

    # ---------- poll (UI invokes every 70 ms live / 250 ms idle) ----------
    def poll(self):
        # Backstop channel: every event also went out via the dispatcher thread,
        # and the UI drops whichever copy arrives second by `seq`.
        evs = []
        try:
            while True:
                evs.append(self._events.get_nowait())
        except queue.Empty:
            pass
        # Lazy: translator pulls google.genai; a module-top import would put the
        # heavy runtime back on the cold start this codebase deliberately avoids.
        from .translator import get_usage
        in_sec, _o, usd = get_usage()
        speaking = any(getattr(getattr(p, "_source", None), "speech_active", False)
                       for p in self.controller._pipelines)
        mode = self.controller.mode
        session = (t("session_active", mode=self._mode_name(mode)) if mode
                   else t("session_idle"))
        from .config import resolve_model, route_engine
        eng = (self.controller.current_engine()
               or route_engine(self.cfg, self.cfg.get("target_language_incoming", "")))
        return {
            "events": evs,
            "usage": t("usage_fmt", min=in_sec / 60, usd=usd),
            "badge": {"text": self._badge[0].lstrip("● ").strip(), "color": self._badge[1]},
            "dotcls": self._badge[2],
            "vad": speaking,
            "level": self.controller.current_level(),
            "latency": self.controller.current_latency(),
            "playing": self.controller.is_playing(),
            "mode": mode,
            "engine": eng,
            "model": resolve_model(self.cfg, eng),
            "session": session,
            "maximized": bool(self._maximized),
            # Sound-check meter level (0..1); only meaningful while the probe runs.
            "sc": round(self._sc_level, 3) if self._sc is not None else None,
            "sc_mic": (round(self._sc_mic_level, 3)
                       if self._sc_mic is not None else None),
        }

    # ---------- helpers ----------
    def _mode_name(self, mode):
        return t(f"mode_{mode}").split("  ")[-1] if mode else ""

    def _mark_custom(self):
        if self.cfg.get("active_profile") != "custom":
            self.cfg["active_profile"] = "custom"

    def _maybe_restart(self):
        """Restart the active session to pick up a config change. Debounced: a
        burst of set_cfg calls (e.g. dragging a slider, rapid dropdown changes)
        collapses into a single restart so we don't spawn racing _start threads
        for every intermediate value."""
        if not self.controller.mode:
            return
        self._restart_token += 1
        token = self._restart_token

        def run():
            # Only the most recent restart request survives the debounce window.
            if token != self._restart_token:
                return
            mode = self.controller.mode
            if mode:
                # A restart of an already-running session: consent was necessarily
                # granted to reach this state, so a settings change must not be
                # blocked by the meeting-consent backstop (it would otherwise tear
                # the session down on any config edit when the user declined
                # "don't show again").
                #
                # Go through _start_thread (not _start directly): endpoint switching
                # CoInitializes this throwaway Timer thread, and _start_thread's
                # finally: shutdown_com() releases the apartment + clears the tid on
                # the same thread. Calling _start directly leaked the apartment and
                # left the tid in win_audio's bookkeeping, faulting a later reused
                # tid with CO_E_NOTINITIALIZED.
                self._start_thread(mode, True)

        # daemon: threading.Timer threads are non-daemon by default, and this
        # one's callback runs a FULL session start (network + PortAudio + COM).
        # A user who changed a setting and closed the window inside the debounce
        # left that thread alive after webview.start() returned — a headless
        # zombie process holding the Voxis.SingleInstance mutex, which made the
        # next launch silently refuse to open until the zombie was killed in
        # Task Manager (field report, 2026-07-10).
        t = threading.Timer(0.4, run)
        t.daemon = True
        t.start()

    def _register_hotkeys(self):
        # RegisterHotKey-based (app/global_hotkey.py), not `keyboard.add_hotkey`:
        # this path is armed for the app's whole lifetime, so it must not carry
        # the low-level global hook `keyboard` installs for that. `keyboard`
        # itself stays in use only for the brief interactive capture_hotkey()
        # recording flow (Settings' "press a key" box), a few seconds at a time.
        from . import global_hotkey
        hk = self.cfg.get("hotkeys", {})
        bindings = {}
        for mode in ("video", "meeting"):
            if hk.get(mode):
                bindings[mode] = (hk[mode], lambda m=mode: self._hotkey(m))
        if hk.get("stop"):
            bindings["stop"] = (hk["stop"], lambda: self._hotkey("stop"))
        if hk.get("overlay"):
            bindings["overlay"] = (hk["overlay"], lambda: self._hotkey("overlay"))
        try:
            global_hotkey.set_bindings(bindings)
        except Exception:
            _log.exception("global hotkey registration failed")

    def _hotkey(self, action):
        if action == "stop":
            if self.controller.mode:
                self.stop()
        elif action == "overlay":
            self.toggle_overlay(self._overlay_win is None)
        elif not self.controller.mode:
            self.start(action)


class _JsApiFacade:
    """Base for an explicit allowlist of methods exposed to a webview's JS.

    pywebview's own leading-underscore convention (`Bridge._save_cfg` etc.) is
    NOT a security boundary: it only controls which names appear in the
    auto-generated `window.pywebview.api` stub object. The actual native
    message-bridge dispatcher (pywebview's edgechromium.on_script_notify ->
    js_bridge_call -> get_nested_attribute) resolves ANY attribute name via a
    raw getattr() with no allowlist or token check, so passing a `Bridge`
    instance directly as `js_api=` would let any JS executing in that window
    invoke every method on it — including the "private" underscore ones
    (config writes, thread starts, report/log building, transcript
    migration...) — by name, with attacker-controlled arguments, via
    `window.chrome.webview.postMessage(...)` directly (bypassing the stub
    object entirely). This class is the actual enforcement point: only names
    listed in a subclass's `_EXPOSED` are reachable from that window's JS,
    full stop. Fails closed — a method not listed here is simply absent from
    `self`, so pywebview logs "Function ... does not exist" and nothing runs.

    When adding a new JS-facing Bridge/HistoryMixin method, add its name to
    the relevant `_EXPOSED` tuple too, or it stays silently unreachable."""

    _EXPOSED: tuple[str, ...] = ()

    def __init__(self, target):
        for name in self._EXPOSED:
            setattr(self, name, getattr(target, name))


class JsApi(_JsApiFacade):
    """Main-window facade. Kept in sync with every `api().X(...)` call in
    app/web/app.js (the only place the shipped UI calls the bridge from)."""

    _EXPOSED = (
        # session lifecycle / polling
        "start", "stop", "poll", "check_auth", "get_init",
        # config
        "get_cfg", "set_cfg", "set_profile", "set_device", "set_hotwords",
        "hotword_stats", "set_voice_gender", "swap_languages",
        # auth / licensing
        "voxis_login", "google_login", "voxis_logout", "voxis_quota",
        "save_keys", "clear_byok",
        # window chrome + hotkeys
        "win_minimize", "win_toggle_max", "win_close", "win_resize",
        "win_begin_drag", "capture_hotkey", "cancel_hotkey", "toggle_overlay",
        # meeting / audio diagnostics
        "meeting_cable_available", "open_cable_download",
        "soundcheck_start", "soundcheck_play_tone", "soundcheck_stop",
        # onboarding / lifecycle prompts
        "whatsnew", "mark_whatsnew_seen", "mark_seen", "mark_onboarding_done",
        "reset_onboarding", "rate_voxis",
        "free_voice_preview", "pro_voice_replay",
        # transcripts / history
        "save_txt", "list_sessions", "load_session", "delete_session",
        "export_session", "open_transcript", "reveal_transcript",
        "open_transcript_folder", "choose_transcript_dir",
        "reset_transcript_dir",
        # problem reports
        "flush_reports", "preview_report", "send_report",
        # navigation
        "open_url", "open_store_page",
    )


class OverlayJsApi(_JsApiFacade):
    """Overlay-window facade. Kept in sync with the `window.pywebview.api.X`
    calls inside `_OVERLAY_HTML`'s own inline <script> below — that HTML only
    ever calls these four."""

    _EXPOSED = ("overlay_poll", "overlay_fit", "overlay_show", "overlay_hide")


_OVERLAY_HTML = """<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
/* Graphite Console language (see index.html): flat graphite, hairline border,
   amber = live/on-air signal. System font on purpose — the overlay is a
   transient always-on-top window and must not stall on a webfont fetch. */
html,body{margin:0;height:100%;overflow:hidden;background:#131518;
  font-family:'Segoe UI Variable Text','Segoe UI',system-ui,sans-serif;-webkit-user-select:none;cursor:default}
#bar{display:flex;align-items:center;gap:16px;min-height:100%;box-sizing:border-box;
  padding:14px 22px;-webkit-app-region:drag;
  background:#16181c;border:1px solid rgba(235,240,245,.12)}
#mark{width:34px;height:34px;flex:none;border-radius:8px;display:grid;place-items:center;
  background:#e9eef3}
#divider{width:3px;align-self:stretch;flex:none;border-radius:3px;margin:2px 0;
  background:#ffb224;box-shadow:0 0 9px rgba(255,178,36,.55)}
#txt{flex:1;color:#f2f5f8;font-size:25px;font-weight:600;line-height:1.34;
  text-shadow:0 1px 5px rgba(0,0,0,.55);max-height:101px;overflow:hidden}
#col{flex:1;display:flex;flex-direction:column;gap:3px;min-width:0}
#brand{font-size:10.5px;font-weight:600;letter-spacing:.12em;color:rgba(233,238,243,.44);
  text-shadow:0 1px 3px rgba(0,0,0,.5);display:none}
</style></head><body>
<div id='bar'>
  <div id='mark'><svg width='19' height='19' viewBox='0 0 1075.8 1075.8'><path fill='#131518' d='M89.65 332.95 L278.17 301.19 L367.78 737.34 L268.17 888.72 Z'/><path fill='#FFB224' d='M219.39 684.87 C278.89 597.47 341.64 519.58 421.23 455.83 C556.55 347.46 794.02 246.48 986.15 187.08 C878.25 251.89 758.69 321.26 640.05 417.53 C543.00 492.74 431.90 634.48 344.32 785.53 L320.60 575.30 Z'/></svg></div>
  <div id='divider'></div>
  <div id='col'>
    <div id='txt'></div>
    <div id='brand'></div>
  </div>
</div>
<script>
const txt=document.getElementById('txt'); const brand=document.getElementById('brand');
let vis=false, lastH=0, lastBrand=null, fast=false;
function fit(){
  txt.scrollTop = txt.scrollHeight;
  const h=Math.ceil(document.getElementById('bar').scrollHeight);
  if(Math.abs(h-lastH)>3){ lastH=h; try{window.pywebview.api.overlay_fit(h);}catch(e){} }
}
async function p(){
  try{
    // One combined bridge call per tick: caption + attribution badge together.
    const r=await window.pywebview.api.overlay_poll();
    const b=(r&&r.badge)||'';
    if(b!==lastBrand){ lastBrand=b; brand.textContent=b||''; brand.style.display=b?'block':'none'; requestAnimationFrame(fit); }
    const x=(r&&r.text)||'';
    fast = !!x;
    if(x){
      if(txt.textContent!==x){ txt.textContent=x; requestAnimationFrame(fit); }
      if(!vis){ vis=true; window.pywebview.api.overlay_show(); }
    } else if(vis){ vis=false; window.pywebview.api.overlay_hide(); }
  }catch(e){}
  // Adaptive: 70 ms while a caption is on screen (subtitle sync is part of the
  // latency budget), 200 ms while blank.
  setTimeout(p, fast?70:200);
}
window.addEventListener('pywebviewready',p);setTimeout(p,400);
</script></body></html>"""


def _set_taskbar_icon(icon_path: str, title: str):
    """Sets an explicit AppUserModelID and updates the window icon so the
    process is grouped under Voxis (not python.exe) in the taskbar.

    Windows-only (Win32 taskbar API). On other platforms window-app grouping is
    handled by the desktop entry (.desktop StartupWMClass), so this no-ops."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Voxis.App.1")
    except Exception:
        pass

    def apply():
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x80, 0, 1
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
        u = ctypes.windll.user32
        for _ in range(40):
            hwnd = u.FindWindowW(None, title)
            if hwnd:
                for size, which in ((32, ICON_BIG), (16, ICON_SMALL)):
                    hicon = u.LoadImageW(0, icon_path, IMAGE_ICON, size, size,
                                         LR_LOADFROMFILE)
                    if hicon:
                        u.SendMessageW(hwnd, WM_SETICON, which, hicon)
                return
            time.sleep(0.25)

    threading.Thread(target=apply, daemon=True).start()


_shutting_down = threading.Lock()


def _shutdown(bridge, grace: float = 8.0):
    """Stop any live session, then GUARANTEE process death.

    Called from the normal exit (webview.start() returned) and from the closing
    watchdog. The stop path crosses COM (endpoint restore), PortAudio teardown
    and the network; any of those wedging after the window is gone would leave a
    headless zombie still holding the Voxis.SingleInstance mutex, so the app
    "won't reopen until killed in Task Manager" (field report, 2026-07-10). Run
    the stop on a daemon thread with a bounded grace, then hard-exit: normal
    interpreter shutdown would itself wait on any straggler non-daemon thread.
    Whoever gets here first owns the teardown; the loser just returns.
    """
    if not _shutting_down.acquire(blocking=False):
        return
    # Stop pushing into a window that is going away: an evaluate_js against a
    # destroyed WebView2 can block until it faults, and the dispatcher holds no
    # state worth draining (poll is gone too at this point).
    try:
        bridge._dispatch_stop.set()
    except Exception:
        pass

    def _stop_session():
        try:
            if bridge.controller.mode:
                # Closing the window is not the same signal as pressing Stop —
                # the funnel needs to tell "watched, then quit the app" apart
                # from "stopped the session and stayed".
                bridge.controller.stop(reason="app_close")
        except Exception:
            _log.debug("final session stop failed", exc_info=True)

    t = threading.Thread(target=_stop_session, daemon=True,
                         name="voxis-final-cleanup")
    t.start()
    t.join(grace)  # final heartbeat + endpoint restore normally take <2 s
    try:
        logging.shutdown()  # flush voxis.log before the hard exit
    except Exception:
        pass
    os._exit(0)


def run(cfg):
    bridge = Bridge(cfg)
    # Auto-select the virtual cable in the background so device enumeration
    # doesn't block the window from appearing.
    threading.Thread(target=_autofill_meeting_devices, args=(cfg,),
                     daemon=True).start()
    # Flush any problem reports queued from a previous offline send. App start is
    # an explicit user context (not a silent background flush) and the payloads
    # already carry the user's original consent. Best-effort, off the UI thread.
    threading.Thread(target=bridge.flush_reports, daemon=True).start()
    icon = icon_path()
    if os.path.exists(icon):
        _set_taskbar_icon(icon, t("app_title"))
    # Restore saved window geometry (size/position), clamped to the minimum.
    geo = cfg.get("window") if isinstance(cfg.get("window"), dict) else {}

    def _geo_num(v, default):
        # A hand-edited / corrupt config with a non-numeric w/h must not crash the
        # launch — fall back to the default like the x/y restore below already does.
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    win_w = max(_geo_num(geo.get("w"), 1180), 940)
    win_h = max(_geo_num(geo.get("h"), 760), 600)
    geo_kwargs = {}
    if isinstance(geo.get("x"), int) and isinstance(geo.get("y"), int):
        # Only restore the saved position if it still lands on a connected
        # display; otherwise (unplugged monitor / dock change) let pywebview
        # center the window so it can't open off-screen and invisible.
        gx, gy = geo["x"], geo["y"]
        try:
            if sys.platform == "win32":
                import ctypes
                u = ctypes.windll.user32
                SM_XV, SM_YV, SM_CXV, SM_CYV = 76, 77, 78, 79  # virtual-screen metrics
                vx, vy = u.GetSystemMetrics(SM_XV), u.GetSystemMetrics(SM_YV)
                vw, vh = u.GetSystemMetrics(SM_CXV), u.GetSystemMetrics(SM_CYV)
            else:
                # Portable across pywebview's GTK/QT backends: union bounding
                # box of every connected display (Windows' virtual-screen
                # metrics equivalent).
                screens = webview.screens
                vx = min(s.x for s in screens)
                vy = min(s.y for s in screens)
                vw = max(s.x + s.width for s in screens) - vx
                vh = max(s.y + s.height for s in screens) - vy
            on_screen = (vx - 8 <= gx <= vx + vw - 100) and (vy - 8 <= gy <= vy + vh - 80)
        except Exception:
            on_screen = True  # fail-open: trust the saved coords if probing fails
        if on_screen:
            geo_kwargs["x"], geo_kwargs["y"] = gx, gy
    # `-webkit-app-region: drag` (index.html's .pywebview-drag-region) drives
    # the titlebar drag natively on Windows/WebView2, so easy_drag stays off
    # there. It does nothing on WebKitGTK (Linux), so Linux dragging is
    # handled by a custom JS handler (index.html) scoped to that same CSS
    # region, calling win_get_pos/win_move_to below -- pywebview's own GTK
    # easy_drag was tried and rejected: it binds button-press/motion to the
    # ENTIRE webview with no concept of `no-drag`, so it fought every button,
    # slider and the custom resize grips for the same mouse events (window
    # lurching erratically instead of following the cursor).
    window = webview.create_window(
        t("app_title"), os.path.join(WEB_DIR, "index.html"),
        js_api=JsApi(bridge), width=win_w, height=win_h, min_size=(940, 600),
        background_color="#0b0c10", frameless=True, easy_drag=False,
        resizable=True, **geo_kwargs,
    )
    if window is None:
        raise RuntimeError("webview.create_window() returned None — main window creation failed")
    bridge._main_window = window
    bridge._win_geom = {"w": win_w, "h": win_h, **{k: geo[k] for k in ("x", "y") if k in geo_kwargs}}
    # Persist size/position/maximized across launches.
    try:
        window.events.resized += bridge._on_win_resized
        window.events.moved += bridge._on_win_moved
        window.events.maximized += bridge._on_win_maximized
        window.events.minimized += bridge._on_win_minimized
        window.events.restored += bridge._on_win_restored
        window.events.closing += bridge._on_win_closing
    except Exception:
        pass
    if geo.get("max"):
        def _restore_max():
            try:
                window.maximize()
                bridge._maximized = True
            except Exception:
                pass
        try:
            window.events.shown += _restore_max
        except Exception:
            pass
    bridge._register_hotkeys()
    if cfg.get("overlay_enabled"):
        bridge.toggle_overlay(True)
    kwargs = {}
    if os.path.exists(icon):
        kwargs["icon"] = icon
    try:
        webview.start(**kwargs)
    except TypeError:
        # Older pywebview without the icon parameter.
        webview.start()
    _shutdown(bridge)
