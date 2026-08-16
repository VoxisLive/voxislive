"""Bridge mixin: session transcript persistence, History panel + export.

Split out of the "god bridge" (`app/webui.py`'s `Bridge` class — see
CLAUDE.md's known-debt note) as its first slice: this domain already
delegated most of its logic to `transcript_store.py`, so the extraction is a
pure move, not a redesign. `Bridge` inherits `HistoryMixin` so every method
here still lands on the single pywebview `js_api` instance under its exact
original name/signature — JS calls `window.pywebview.api.list_sessions()`
etc. unchanged.
"""
import logging
import os
import threading
import time
from typing import TYPE_CHECKING

import webview

from . import APP_VERSION, transcript_store, voxis_client
from .config import IS_OFFICIAL_RELEASE
from .i18n import t
from .paths import legacy_transcripts_dir, transcripts_dir

if TYPE_CHECKING:
    from .pipeline import ModeController
    from .webui import _LegState

_log = logging.getLogger("voxis.webui")

# Allowed transcript file extensions for the open/reveal bridge (path-traversal +
# type guard). JSON is the canonical record; the rest are on-demand exports.
_TRANSCRIPT_EXTS = (".json", ".txt", ".srt", ".vtt")

_DUP_NORM = str.maketrans("", "", ".,;:!?…\"'()-—–")
_DUP_LEAD = ("yani", "ve", "ama", "so", "and", "but", "well", "okay", "tamam")

INLINE_REPEAT_MIN_WORDS = 5     # below this a repeat is plausible speech


def _strip_inline_repeat(text: str, threshold: float = 0.9) -> str:
    """Drop an engine re-speak that repeats INSIDE one caption line.

    The cross-turn guard (_near_duplicate) only compares whole turns, so it
    never saw this shape:

        A. <connective>, A. <tail>

    where A is a full clause the engine emitted twice — measured at 4-8 % of all
    caption words in two podcast sessions, identical in both runs of the same
    video (2026-07-29). The AUDIO says A once; only the caption carries it
    twice, which also inflated how much text looked "never spoken".

    Conservative by construction, because this DELETES text: the repeat must be
    at least INLINE_REPEAT_MIN_WORDS long, must not overlap its own first copy,
    and must match at `threshold`. A short echo ("Evet. Evet.") is left alone —
    that is plausible speech. Whatever follows the second copy is kept.
    """
    w = text.split()
    n = len(w)
    if n < 2 * INLINE_REPEAT_MIN_WORDS:
        return text
    key = [x.translate(_DUP_NORM).casefold() for x in w]
    # Candidate restarts: positions that repeat the line's opening words. Cheap
    # filter first — the full ratio check runs on a handful of positions, not on
    # every (length, offset) pair, so this stays off the caption path's budget.
    probe = key[:3]
    starts = [i for i in range(INLINE_REPEAT_MIN_WORDS, n - INLINE_REPEAT_MIN_WORDS + 1)
              if key[i:i + 3] == probe]
    if not starts:
        return text
    import difflib
    for i in starts:
        ln = min(i, n - i)                      # longest non-overlapping copy
        while ln >= INLINE_REPEAT_MIN_WORDS:
            # The last words must match EXACTLY, or a fuzzy match is free to run
            # one word past the real repeat and eat the first word of the tail —
            # `threshold` tolerates a single mismatch in ten, and that mismatch
            # would be a word the speaker actually said.
            if (key[ln - 1] == key[i + ln - 1]
                    and difflib.SequenceMatcher(None, key[:ln], key[i:i + ln],
                                                autojunk=False).ratio() >= threshold):
                return " ".join(w[:ln] + w[i + ln:])
            ln -= 1
    return text


def _near_duplicate(prev: str, cur: str, threshold: float = 0.9) -> bool:
    """True when `cur` is an engine re-speak of `prev` rather than fresh speech.

    The re-speak after an internal reconnect is REGENERATED, so it returns
    lightly reworded — different punctuation, or a leading connective bolted on.
    Exact equality misses those, and the echo lands in the transcript as a
    second turn that was never spoken aloud."""
    def norm(s):
        w = s.translate(_DUP_NORM).casefold().split()
        while w and w[0] in _DUP_LEAD:
            del w[0]
        return w

    a, b = norm(prev), norm(cur)
    if not a or not b:
        return False
    if a == b:
        return True
    # Length alone rules most pairs out before the O(n^2) ratio is worth running.
    if min(len(a), len(b)) / max(len(a), len(b)) < threshold:
        return False
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


class HistoryMixin:
    """Session record building, save/auto-export, and the History panel API.

    Depends on attributes/methods set up by `Bridge.__init__` and defined
    elsewhere on `Bridge` (`_text_lock`, `_save_lock`, `_turns`, `_legs`,
    `_session_*`, `_last_saved_file`, `cfg`, `_main_window`, `_emit_status`,
    `_pop_source`, `_pending_source`, `_last_turn_text`, `controller`) — this
    is a mixin onto the one `Bridge` instance, not a standalone object.
    """

    if TYPE_CHECKING:
        # Declared, never assigned here: these live on Bridge.__init__ (or on
        # other Bridge domains) and are only typed here so pyright can check
        # this mixin's own body. Keep in sync with Bridge.__init__ if a
        # depended-on attribute's type changes there.
        cfg: dict
        controller: "ModeController"
        _text_lock: threading.RLock
        _save_lock: threading.Lock
        _legs: dict[str, "_LegState"]
        _lines: list[str]
        _turns: list[dict]
        _session_events: list[dict]
        _src_track: list[dict]
        _audio_track: list[dict]
        _session_dirname: str | None
        _last_saved_file: str | None
        _main_window: "webview.Window | None"
        _summary_lock: threading.Lock
        _summary_busy: bool

        def _emit_status(self, msg, level: str = "info") -> None: ...
        def _save_cfg(self) -> bool: ...
        def _pop_source(self, cutoff: float | None = None,
                        st: "_LegState | None" = None) -> tuple[int | None, str]: ...
        def _pending_source(self, st: "_LegState | None" = None) -> str: ...
        def _last_turn_text(self, leg: str) -> str: ...
        def _put_event(self, ev) -> None: ...
        def _is_paid(self) -> bool: ...
        def _ensure_user_id(self) -> str | None: ...

    def _flush_turns(self):
        """Fold the in-progress turn into the structured log so a session that is
        stopped mid-utterance still records its last line. Idempotent.

        Runs at stop() before the translators are joined, so it can race a live
        _on_text — take the same lock to keep the shared buffers consistent.

        Both meeting legs are folded, then the shared turn list is re-sorted so
        the record stays one chronological timeline regardless of which side
        happened to be mid-utterance at stop."""
        with self._text_lock:
            for leg, st in self._legs.items():
                self._flush_leg_locked(leg, st)
            self._turns.sort(key=lambda x: x.get("t", 0.0))

    def _flush_leg_locked(self, leg, st):
            tail = _strip_inline_repeat(st.cur_line.strip())
            if not tail:
                # No pending translation. If the whole session produced NO
                # translation at all (Qwen can drop its text stream mid-session
                # while source ASR keeps arriving), fold the captured source alone
                # so the session is still saved — a bilingual QA user relies on the
                # source side to inspect segmentation even when the translation is
                # lossy — instead of being reported as "nothing to save" and lost.
                # A normal session already has turns/lines, so this never adds a
                # spurious trailing source-only turn to it.
                pend_src = self._pending_source(st)
                if pend_src and not self._turns and not self._lines:
                    if not self._session_start:
                        self._session_start = time.time()
                    self._turns.append({
                        "t": 0.0, "dir": "out", "src": pend_src, "text": "",
                    })
                return
            # Same re-speak guard the streaming path applies (see _near_duplicate):
            # an exact tail repeat is always the echo, and a long reworded one is
            # too. A short reworded line stays — it is plausible dialogue.
            prev = self._last_turn_text(leg)
            if prev and (prev == tail
                         or (len(tail) >= 20 and _near_duplicate(prev, tail))):
                return
            if not self._session_start:
                self._session_start = time.time()
            start = st.turn_start or self._session_start
            # This is the session's LAST turn — take everything remaining
            # unconditionally (cutoff=None); there is no later turn to hand
            # off leftover source to.
            spk, src = self._pop_source(None, st)
            own_src = src or None
            turn = {
                "t": max(0.0, start - self._session_start),
                "dir": "out",
                "src": own_src,
                "text": tail,
            }
            if spk is not None:
                turn["spk"] = spk
            if getattr(self.controller, "mode", None) == "meeting":
                turn["leg"] = leg
            st.cur_line = ""          # folded — a second flush must be a no-op
            self._turns.append(turn)

    def _build_record(self):
        return transcript_store.build_record(
            self._session_start or time.time(),
            self._turns,
            app_version=APP_VERSION,
            mode=self.controller.mode or "",
            ui_language=self.cfg.get("ui_language", ""),
            target_in=self.cfg.get("target_language_incoming", ""),
            target_out=self.cfg.get("target_language_outgoing", ""),
            events=list(self._session_events),
            source_track=list(self._src_track),
            audio_track=list(self._audio_track),
        )

    def save_txt(self, silent=False):
        with self._save_lock:
            return self._save_txt_locked(silent=silent)

    def _save_txt_locked(self, silent=False):
        """Persist the session as a JSON record (the canonical, timestamped
        store). Backs the 'Save transcript' button; also called on stop.
        Returns {ok, path, file} on success (the JS renders open/reveal actions
        from it) or False on nothing-to-save / write failure."""
        self._flush_turns()
        with self._text_lock:
            has_turns = bool(self._turns)
            record = self._build_record() if has_turns else None
            subdir = self._session_dirname
        if not has_turns:
            # Nothing new in the buffer. But if this session was already
            # auto-saved on stop, re-surface that file (path + open/reveal) so a
            # post-stop "Save transcript" click confirms the save instead of
            # claiming there is nothing to save.
            if self._last_saved_file and os.path.exists(self._last_saved_file):
                if not silent:
                    self._emit_status(t("saved_to", path=self._last_saved_file))
                return {"ok": True, "path": self._last_saved_file,
                        "file": os.path.basename(self._last_saved_file)}
            if not silent:
                self._emit_status(t("no_transcript"))
            return False
        assert record is not None  # record is built iff has_turns, and that branch returned above
        primary = self._transcript_dir()
        # Save into this session's own folder (same one the recorder wrote its WAVs
        # into), so the whole session stays self-contained. subdir may be None for a
        # save with no active session — save_record then derives it from the record.
        path = None
        try:
            path = transcript_store.save_record(primary, record, subdir=subdir)
        except OSError:
            # Documents can be blocked (Controlled Folder Access) or unwritable —
            # never lose a transcript: retry into the legacy AppData dir and report
            # THAT path so the user can still find it.
            _log.exception("transcript save to %s failed; retrying legacy dir", primary)
            legacy = legacy_transcripts_dir()
            try:
                path = transcript_store.save_record(legacy, record, subdir=subdir)
            except OSError:
                _log.exception("transcript save failed")
                if not silent:
                    self._emit_status(t("err_save_failed"), "error")
                return False
        self._session_file = path
        if not silent:
            self._emit_status(t("saved_to", path=path))
        self._auto_export(record, path)
        # Background disk housekeeping: prune old/orphaned transcript folders (>90 days / >500 count)
        threading.Thread(target=transcript_store.prune_transcripts, args=(primary,), daemon=True).start()
        return {"ok": True, "path": path, "file": os.path.basename(path)}

    def _auto_export(self, record: dict, json_path: str):
        """Generate the user's configured caption formats (Settings > General
        > "Otomatik kayıt formatları") beside the JSON, on every save — the
        JSON alone required an extra trip through History to get a TXT/SRT/VTT
        copy of the same session. Best-effort: never raises into the caller,
        since a failed convenience export must not make save_txt() itself
        look like it failed."""
        fmts = [f for f in ("txt", "srt", "vtt") if self.cfg.get(f"auto_export_{f}")]
        if not fmts or not json_path.endswith(".json"):
            return
        base = json_path[:-len(".json")]
        for fmt in fmts:
            try:
                content, ext = transcript_store.export(record, fmt, bilingual=True)
                with open(base + "_bilingual." + ext, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                _log.exception("auto-export %s failed", fmt)

    # ---------- transcript directory + reveal ----------
    def _transcript_dir(self) -> str:
        """Active save directory (Documents\\Voxis\\Transcripts by default, or the
        user's configured folder)."""
        return transcripts_dir(self.cfg)

    def _transcript_dirs(self) -> list:
        """Directories to scan for saved sessions: the active dir first, then the
        legacy AppData dir (so pre-move sessions still appear even if migration
        was skipped/partial). Deduped, order-preserving."""
        dirs, seen = [], set()
        for d in (self._transcript_dir(), legacy_transcripts_dir()):
            key = os.path.normcase(os.path.abspath(d))
            if key not in seen:
                seen.add(key)
                dirs.append(d)
        return dirs

    def _safe_transcript_name(self, file: str) -> bool:
        """Reject path traversal + non-transcript files (the bare filename must
        equal its own basename and carry a known extension)."""
        return bool(file) and os.path.basename(file) == file \
            and file.lower().endswith(_TRANSCRIPT_EXTS)

    def _find_transcript(self, file: str) -> str | None:
        """Full path of a saved file, searched across the active + legacy dirs.
        Returns None if the name is unsafe or the file does not exist.

        Handles both the per-session-folder layout (`voxis_<stamp>/<file>`, current)
        and the legacy flat layout (`<file>` directly in the dir). `file` stays a
        bare basename (traversal-guarded); the session subfolder is resolved here,
        never trusted from the caller."""
        if not self._safe_transcript_name(file):
            return None
        for d in self._transcript_dirs():
            path = os.path.join(d, file)
            if os.path.isfile(path):
                return path  # legacy flat
            # Nested: scan this dir's per-session folders for the file.
            try:
                subs = os.listdir(d)
            except OSError:
                continue
            for sub in subs:
                if not sub.startswith("voxis_"):
                    continue
                cand = os.path.join(d, sub, file)
                if os.path.isfile(cand):
                    return cand
        return None

    def _migrate_transcripts(self):
        """One-time move of pre-1.0.26 transcripts from the legacy AppData dir into
        the active (user-facing) dir. On the Store MSIX the legacy read resolves
        through the container's LocalCache view while the write lands in real
        Documents — this also rescues files Windows would delete on uninstall.
        Best-effort: any per-file failure is skipped, never fatal."""
        try:
            import shutil
            src = legacy_transcripts_dir()
            dst = self._transcript_dir()
            if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
                return
            try:
                names = [n for n in os.listdir(src)
                         if n.startswith("voxis_") and n.lower().endswith(_TRANSCRIPT_EXTS)]
            except OSError:
                return
            if not names:
                return
            os.makedirs(dst, exist_ok=True)
            for n in names:
                target = os.path.join(dst, n)
                if os.path.exists(target):
                    continue  # never clobber a file already in the new location
                try:
                    shutil.move(os.path.join(src, n), target)
                except OSError:
                    pass  # locked / permission — leave it; it still lists via legacy
        except Exception:
            _log.exception("transcript migration skipped")

    def open_transcript(self, file: str) -> dict:
        """Open a saved transcript file in its default app (JSON in the editor,
        etc.). Traversal-guarded; searches the active + legacy dirs."""
        path = self._find_transcript(file)
        if not path:
            return {"ok": False, "error": "not_found"}
        try:
            os.startfile(path)
            return {"ok": True}
        except OSError as e:
            _log.exception("open_transcript failed")
            return {"ok": False, "error": str(e)}

    def reveal_transcript(self, file: str) -> dict:
        """Open Explorer with the transcript file selected ('Open containing
        folder'). Also proves to the user where the file actually lives."""
        path = self._find_transcript(file)
        if not path:
            return {"ok": False, "error": "not_found"}
        try:
            import subprocess
            # explorer /select, highlights the file in its folder. Not shell=True;
            # path is validated + normalized so no argument injection is possible.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return {"ok": True}
        except OSError as e:
            _log.exception("reveal_transcript failed")
            return {"ok": False, "error": str(e)}

    def open_transcript_folder(self) -> dict:
        """Open the active transcript folder in Explorer (creating it if needed)."""
        d = self._transcript_dir()
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
            return {"ok": True, "path": d}
        except OSError as e:
            _log.exception("open_transcript_folder failed")
            return {"ok": False, "error": str(e)}

    def choose_transcript_dir(self) -> dict:
        """Folder-picker for a custom transcript directory. Validates writability
        before persisting so a bad choice can't silently break saving."""
        win = self._main_window
        if win is None:
            return {"ok": False, "error": "no_window"}
        try:
            sel = win.create_file_dialog(webview.FileDialog.FOLDER)
        except Exception:
            _log.exception("choose_transcript_dir dialog failed")
            return {"ok": False, "error": "dialog_failed"}
        if not sel:
            return {"ok": False, "cancelled": True}
        # create_file_dialog always returns a sequence of selected paths (never
        # a bare str), even for a single-selection FileDialog.FOLDER dialog.
        folder = sel[0]
        # Writability probe: create + remove a temp file so we never persist a
        # directory the app cannot actually write transcripts into.
        probe = os.path.join(folder, ".voxis_write_test")
        try:
            with open(probe, "w", encoding="utf-8") as f:
                f.write("")
            os.remove(probe)
        except OSError:
            return {"ok": False, "error": "unwritable"}
        self.cfg["transcript_dir"] = folder
        self._save_cfg()
        return {"ok": True, "path": folder}

    def reset_transcript_dir(self) -> dict:
        """Clear the custom folder override; revert to the built-in default."""
        self.cfg["transcript_dir"] = ""
        self._save_cfg()
        return {"ok": True, "path": self._transcript_dir()}

    # ---------- transcript history + export ----------
    def list_sessions(self) -> list:
        """Newest-first summaries of saved sessions for the history panel, merged
        across the active + legacy dirs (deduped by filename, active wins)."""
        merged, seen = [], set()
        for d in self._transcript_dirs():
            for rec in transcript_store.list_records(d):
                name = rec.get("file")
                if name in seen:
                    continue
                seen.add(name)
                merged.append(rec)
        merged.sort(key=lambda r: r.get("started", 0.0), reverse=True)
        return merged

    def load_session(self, file: str) -> dict | None:
        """Load one saved session's full record. `file` is the bare filename
        returned by list_sessions; path traversal is rejected."""
        if not file or os.path.basename(file) != file or not file.endswith(".json"):
            return None
        path = self._find_transcript(file)
        if not path:
            return None
        try:
            return transcript_store.load_record(path)
        except (OSError, ValueError, RecursionError):
            # RecursionError: json's parser recurses per nesting level, so a
            # pathologically deep record (hand-edited, corrupted) can blow the
            # stack before any of our own validation runs -- treat it as just
            # another unreadable record, not a crash (see config.load_config
            # for the same fix on the config.json path).
            return None

    def star_session(self, file: str, starred: bool) -> bool:
        """Pin/unpin a saved session from History. Read-modify-write (the star
        state changes long after the session was saved, not during save_txt's
        own flow) — schema-additive on disk (transcript_store's `starred`
        field docstring), and exempts the session from prune_transcripts's
        age/count housekeeping."""
        if not file or os.path.basename(file) != file or not file.endswith(".json"):
            return False
        path = self._find_transcript(file)
        if not path:
            return False
        try:
            record = transcript_store.load_record(path)
        except (OSError, ValueError, RecursionError):
            return False
        if starred:
            record["starred"] = True
        else:
            record.pop("starred", None)
        try:
            transcript_store.overwrite_record(path, record)
        except OSError:
            return False
        transcript_store.invalidate_summary_cache(path)
        return True

    def edit_session(self, file: str, turns: list) -> bool:
        """Overwrite a saved session's turn text/source (History's edit mode).

        `turns` is a list of {"text", "src"} patches aligned by INDEX to the
        record's own turns — only those two fields are writable; timing,
        speaker label and meeting leg are preserved untouched. A turn left
        empty on both sides after editing is dropped, same as build_record's
        own cleaning rule (a turn must carry something to exist at all).
        `export_session` always reads back from the saved record, so a fixed
        transcript is automatically what gets exported — no separate code
        path needed there."""
        if not file or os.path.basename(file) != file or not file.endswith(".json"):
            return False
        if not isinstance(turns, list):
            return False
        path = self._find_transcript(file)
        if not path:
            return False
        try:
            record = transcript_store.load_record(path)
        except (OSError, ValueError, RecursionError):
            return False
        existing = record.get("turns")
        if not isinstance(existing, list):
            return False
        for i, patch in enumerate(turns):
            if i >= len(existing) or not isinstance(patch, dict):
                continue
            turn = existing[i]
            if not isinstance(turn, dict):
                continue
            if "text" in patch:
                turn["text"] = str(patch.get("text") or "").strip()
            if "src" in patch:
                turn["src"] = str(patch.get("src") or "").strip()
        record["turns"] = [t for t in existing
                           if isinstance(t, dict)
                           and ((t.get("src") or "").strip() or (t.get("text") or "").strip())]
        try:
            transcript_store.overwrite_record(path, record)
        except OSError:
            return False
        transcript_store.invalidate_summary_cache(path)
        return True

    def delete_session(self, file: str) -> bool:
        if not file or os.path.basename(file) != file or not file.endswith(".json"):
            return False
        path = self._find_transcript(file)
        if not path:
            return False
        parent = os.path.dirname(path)
        # A self-contained session folder (voxis_<stamp>/ directly under a
        # transcripts dir) is removed whole — JSON + WAVs + caption exports —
        # so deleting a session leaves nothing orphaned. Legacy flat records
        # remove just the single JSON. The grandparent==root check keeps rmtree
        # from ever escaping a known transcripts directory.
        try:
            roots = {os.path.normcase(os.path.abspath(d))
                     for d in self._transcript_dirs()}
            grandparent = os.path.normcase(os.path.abspath(os.path.dirname(parent)))
            if os.path.basename(parent).startswith("voxis_") and grandparent in roots:
                import shutil
                shutil.rmtree(parent)
            else:
                os.remove(path)
            # Drop the History summary cached for this record so a deleted
            # session cannot survive in the next listing.
            transcript_store.invalidate_summary_cache(path)
            return True
        except OSError:
            return False

    def export_session(self, file: str, fmt: str, bilingual: bool = True) -> dict:
        """Render a saved session to TXT/SRT/VTT next to its JSON. `bilingual`
        keeps the source line alongside the translation (default) or emits a
        translated-only file. Returns {ok, path?, file?, error?}. No tier gating —
        available on every build."""
        if not file or os.path.basename(file) != file or not file.endswith(".json"):
            return {"ok": False, "error": "not_found"}
        src_path = self._find_transcript(file)
        record = self.load_session(file)
        if record is None or src_path is None:
            return {"ok": False, "error": "not_found"}
        bilingual = bool(bilingual)
        try:
            content, ext = transcript_store.export(record, fmt, bilingual=bilingual)
        except ValueError:
            return {"ok": False, "error": "bad_format"}
        # Write the export beside its source JSON (wherever that turned out to be).
        # Bilingual and translated-only variants get distinct names so exporting
        # both formats of the same session never overwrites the other.
        suffix = "_bilingual" if bilingual else ""
        out_path = os.path.join(os.path.dirname(src_path),
                                file[:-len(".json")] + suffix + "." + ext)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            _log.exception("transcript export failed")
            self._emit_status(t("err_save_failed"), "error")
            return {"ok": False, "error": "write_failed"}
        self._emit_status(t("saved_to", path=out_path))
        return {"ok": True, "path": out_path, "file": os.path.basename(out_path)}

    # ---------- post-session AI summary ----------
    def _can_summarize(self) -> bool:
        """Paid tier only on the official SaaS build — a free/taste account must
        never spend a Gemini call this way (2026-08-12 cost-pressure policy: see
        CLAUDE.md's engine-routing-cost-policy note). The OSS/BYOK build has no
        tiers at all and pays for its own key directly, so it stays available
        there unconditionally."""
        return (not IS_OFFICIAL_RELEASE) or self._is_paid()

    def _summary_api_key(self) -> str | None:
        """A plain (non-routed) Gemini key. SaaS: voxis_client.get_session_key()
        with NO caps/target always answers the server's legacy backward-compat
        branch, which is Gemini regardless of the per-target Qwen routing policy
        — no server change needed for this feature. OSS/BYOK: the user's own
        configured key."""
        if not IS_OFFICIAL_RELEASE:
            from . import byok_store
            uid = self._ensure_user_id()
            keys = byok_store.load_byok(uid) if uid else {}
            return keys.get("gemini")
        key, *_rest, _err = voxis_client.get_session_key()
        return key

    def generate_summary(self, file: str) -> dict:
        """Kick off an AI summary of a saved session. Returns immediately —
        the model call runs off the UI thread; progress arrives as
        ('summary', {state, code, ...}) events, same shape/contract as
        free_voice_preview's ('preview', ...) events: JS localizes `code`, no
        raw string ever crosses this boundary."""
        if not self._can_summarize():
            return {"ok": False, "code": "not_allowed"}
        if not self._safe_transcript_name(file):
            return {"ok": False, "code": "not_found"}
        with self._summary_lock:
            if self._summary_busy:
                return {"ok": False, "code": "busy"}
            self._summary_busy = True
        threading.Thread(target=self._summary_thread, args=(file,), daemon=True).start()
        return {"ok": True}

    def _summary_thread(self, file: str):
        try:
            path = self._find_transcript(file)
            if not path:
                self._summary_event("error", "not_found")
                return
            try:
                record = transcript_store.load_record(path)
            except (OSError, ValueError, RecursionError):
                self._summary_event("error", "not_found")
                return
            key = self._summary_api_key()
            if not key:
                self._summary_event("error", "no_key")
                return
            self._summary_event("loading", None)
            from . import session_summary
            try:
                text = session_summary.generate(key, record)
            except session_summary.SummaryUnavailable:
                self._summary_event("error", "failed")
                return
            record["summary"] = text
            try:
                transcript_store.overwrite_record(path, record)
            except OSError:
                self._summary_event("error", "failed")
                return
            transcript_store.invalidate_summary_cache(path)
            self._summary_event("done", None, summary=text)
        except Exception:
            _log.exception("generate_summary failed")
            self._summary_event("error", "failed")
        finally:
            with self._summary_lock:
                self._summary_busy = False

    def _summary_event(self, state, code, **extra):
        self._put_event(("summary", {"state": state, "code": code, **extra}))
