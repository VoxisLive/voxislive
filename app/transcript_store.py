"""Session transcript persistence + caption export.

Each translation session is saved as one JSON file under the user's
`transcripts/` directory. The JSON is the canonical record (timestamped,
bilingual where a source transcription was captured); TXT / SRT / VTT are
rendered on demand from it.

Wire format (schema v1):

    {
      "version": 1,
      "started": 1718700000.0,          # epoch seconds (session start)
      "started_iso": "2026-06-18T12:00:00",
      "app_version": "x.y.z",
      "mode": "video" | "meeting" | "",
      "ui_language": "tr",
      "target_in": "tr",                # incoming target language code
      "target_out": "en",               # outgoing target language code
      "turns": [
        {"t": 0.0, "dir": "out", "src": "original ...", "text": "translated ...",
         "spk": 1},
        ...
      ]
    }

`t` is the turn's offset in seconds from session start. The translate model is
natively simultaneous and stays a few seconds behind the speaker, so `t` is an
approximate caption sync, not a frame-accurate cue — adequate for SRT/VTT.

`spk` (optional, additive to schema v1) is the anonymous speaker label from the
local speaker-change tracker (1-based session-scoped int; see app/speaker_id).
Exports render it as a language-neutral "S1:"/"S2:" prefix — only when the
session actually saw more than one speaker, so single-voice transcripts stay
clean.

`source_track` (optional, additive, top level) is the input-transcription stream
with the time each stretch ARRIVED, kept independently of how it was paired onto
turns. A turn's own `src` is a best-effort pairing built from a fixed lag
estimate; where that estimate is wrong the pairing is wrong, and with only the
paired result on disk the error could not even be measured after the fact. This
track is the raw material a corrected pairing can be derived and validated
against. Omitted when empty.

`audio_track` (optional, additive, top level) is the OUTPUT counterpart of
`source_track`: cumulative seconds of translated speech the engine produced,
sampled while captions flow. A stretch where the caption timeline advances but
this does not is text that was never spoken aloud.

`leg` (optional, additive) is the meeting direction a turn belongs to —
"incoming" (the other party, translated for the user) or "outgoing" (the user,
translated for the other party). Written only in meeting mode, so a Video/Game
record carries no `leg` at all and renders exactly as it always did. Exports
prefix every turn of a two-way record with the localized side name, because in
a meeting the sides alternate constantly and an omitted tag would read as "same
side as before" precisely when it is not.

`starred` (optional, additive, top level) marks a session the user pinned from
History. Written only when true — an unstarred record carries no key at all, so
every record saved before starring existed stays byte-identical. Set well after
the session ends (a read-modify-write via `overwrite_record`, not part of
`build_record`/`save_record`'s normal save flow) and exempts the session from
`prune_transcripts`'s age/count housekeeping.

`summary` (optional, additive, top level) is a user-requested AI recap of the
session (see `app/session_summary.py`), written the same read-modify-write way
as `starred`. `render_txt` prepends it as a header block above the turns;
SRT/VTT are timed caption formats and never carry it.
"""
import json
import os
import tempfile
import threading
import time

from .i18n import t as t_

SCHEMA_VERSION = 1
# Minimum on-screen duration for a caption cue (seconds) when we cannot derive a
# longer span from the next turn's start — keeps the last cue readable.
MIN_CUE_S = 1.6
# Maximum cue duration so a long gap before the next turn doesn't leave a caption
# frozen on screen for the whole pause.
MAX_CUE_S = 7.0
_SAVE_LOCK = threading.Lock()


def session_dir_name(started: float) -> str:
    """Canonical per-session FOLDER name keyed on the session start time.

    Each session is self-contained in its own directory (transcript JSON, caption
    exports, and the optional dual-track WAVs all share this folder + stamp), so a
    whole session can be archived or copied as one unit and file names never
    collide across sessions. Ivo's request, 1.0.28."""
    return time.strftime("voxis_%Y-%m-%d_%H-%M-%S", time.localtime(started))


def session_filename(started: float) -> str:
    """Canonical per-session JSON filename keyed on the session start time."""
    return session_dir_name(started) + ".json"


def build_record(started, turns, *, app_version="", mode="",
                 ui_language="", target_in="", target_out="", events=(),
                 source_track=(), audio_track=()) -> dict:
    """Assemble a schema-v1 record from the in-memory turn list. `turns` is a
    list of {"t", "dir", "src", "text"} dicts (src may be empty).

    `events` is the optional engine-lifecycle log ({"t", "msg"}); it is written
    only when non-empty, so the on-disk shape of an uneventful session — and
    every record written before this existed — stays byte-identical."""
    record = {
        "version": SCHEMA_VERSION,
        "started": float(started),
        "started_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
        "app_version": app_version,
        "mode": mode or "",
        "ui_language": ui_language or "",
        "target_in": target_in or "",
        "target_out": target_out or "",
        "turns": [
            {
                "t": float(turn.get("t", 0.0)),
                "dir": turn.get("dir", "out"),
                "src": (turn.get("src") or "").strip(),
                "text": (turn.get("text") or "").strip(),
                **({"spk": int(turn["spk"])} if turn.get("spk") is not None else {}),
                **({"leg": turn["leg"]} if turn.get("leg") else {}),
            }
            for turn in turns
            if ((turn.get("src") or "").strip()
                or (turn.get("text") or "").strip())
        ],
    }
    clean = [{"t": float(e.get("t", 0.0)), "msg": str(e.get("msg", "")).strip()}
             for e in (events or []) if str(e.get("msg", "")).strip()]
    if clean:
        record["events"] = clean
    # Whitelisted the same way turns are, so the Bridge's internal bookkeeping
    # (its merge watermark) cannot leak into the file.
    track = [
        {
            "t": float(e.get("t", 0.0)),
            "text": str(e.get("text", "")).strip(),
            **({"leg": e["leg"]} if e.get("leg") else {}),
        }
        for e in (source_track or []) if str(e.get("text", "")).strip()
    ]
    if track:
        record["source_track"] = track
    # Cumulative seconds of translated speech, sampled on the caption clock. Its
    # slope against the turn timeline is what shows a stretch that was captioned
    # but never spoken.
    atrack = [{"t": float(e.get("t", 0.0)), "sec": round(float(e.get("sec", 0.0)), 3)}
              for e in (audio_track or [])]
    if atrack:
        record["audio_track"] = atrack
    return record


def save_record(directory: str, record: dict, *, subdir: str | None = None) -> str:
    """Persist a record JSON inside its own per-session folder under `directory`
    (the transcripts root), returning the written path.

    Layout: `<directory>/voxis_<stamp>/voxis_<stamp>.json`. The folder + file share
    one stamp so the JSON, its caption exports, and the optional WAVs form a
    self-contained, copy-as-one-unit set.

    `subdir` lets the caller pin the folder name (e.g. the live session already
    created it at start, so the recorder's WAVs and this JSON land together);
    otherwise it is derived from the record's start time. The JSON filename always
    matches the folder stamp so all of a session's files share it."""
    started = record.get("started", time.time())
    name = subdir or session_dir_name(started)
    session_dir = os.path.join(directory, name)
    os.makedirs(session_dir, exist_ok=True)
    path = os.path.join(session_dir, name + ".json")
    # A stop-time autosave and a manual Save click can target the same session.
    # Serialize them and publish a fully-fsynced temp file atomically so a crash
    # or overlapping write can never truncate the last good transcript.
    with _SAVE_LOCK:
        fd, tmp = tempfile.mkstemp(
            dir=session_dir, prefix=f".{name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            # Best-effort directory sync makes the rename durable on POSIX.
            if os.name != "nt":
                try:
                    dir_fd = os.open(session_dir, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    pass
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    return path


def load_record(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def overwrite_record(path: str, record: dict) -> None:
    """Atomically rewrite an EXISTING record file in place, at whatever path it
    already lives at (legacy flat or the current per-session-folder layout) —
    the write a post-save mutation (star, edit) needs, as opposed to
    save_record's fresh-session layout decisions. Same temp-file + fsync +
    atomic-replace guarantee, and shares _SAVE_LOCK so a concurrent auto-export
    save and a manual edit can never interleave into a torn file."""
    session_dir = os.path.dirname(path)
    with _SAVE_LOCK:
        fd, tmp = tempfile.mkstemp(dir=session_dir, prefix=".tmp.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            if os.name != "nt":
                try:
                    dir_fd = os.open(session_dir, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    pass
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


def _iter_record_paths(directory: str):
    """Yield full paths of every session JSON under `directory`, covering both the
    per-session-folder layout (`voxis_<stamp>/voxis_<stamp>.json`, current) and the
    legacy flat layout (`voxis_<stamp>.json` directly in the root, pre-1.0.28)."""
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if not name.startswith("voxis_"):
            continue
        full = os.path.join(directory, name)
        if name.endswith(".json") and os.path.isfile(full):
            yield full  # legacy flat record
        elif os.path.isdir(full):
            try:
                inner = os.listdir(full)
            except OSError:
                continue
            for m in inner:
                if m.startswith("voxis_") and m.endswith(".json"):
                    fp = os.path.join(full, m)
                    if os.path.isfile(fp):
                        yield fp


# Summary cache for list_records, keyed by abspath -> (mtime_ns, size, summary).
#
# The docstring below says the listing works "without loading every turn body",
# but it did exactly that: the whole record was parsed just to read four header
# fields, a turn count and an 80-char preview. Parsing is cheap once the file is
# in the page cache (~0.06 ms each) -- the cost is the per-file OPEN on a cold
# one, which on Windows also drags in the AV filter: measured 14 ms per file, so
# the first History open after launch grew linearly with session count (~1 s at
# 68 sessions, ~7 s at the 500-file prune cap, scanned for BOTH the active and
# legacy dirs).
#
# The cache is therefore PERSISTED: an in-process dict alone would still pay the
# full cold cost on the first open of every launch, which is the case that
# actually hurts. Revalidation is (mtime_ns, size) from os.stat -- directory
# metadata, not a file open, so it does not re-trigger the scan. Any problem with
# the index (missing, corrupt, unwritable) simply falls back to reading records.
_SUMMARY_CACHE: dict[str, tuple[int, int, dict]] = {}
_SUMMARY_CACHE_LOCK = threading.Lock()
_INDEX_LOADED = False
_INDEX_DIRTY = False
# Lives in the app data dir, NOT in the user's transcripts folder: that folder is
# theirs (Documents\Voxis\Transcripts) and must not collect app bookkeeping.
_INDEX_NAME = "transcript_index.json"


def _index_path() -> str | None:
    try:
        from .paths import user_path  # lazy: avoids an import cycle at module load
        return user_path(_INDEX_NAME)
    except Exception:
        return None


def _load_index_locked() -> None:
    """Populate _SUMMARY_CACHE from disk once per process. Caller holds the lock."""
    global _INDEX_LOADED
    if _INDEX_LOADED:
        return
    _INDEX_LOADED = True                      # set first: one attempt, ever
    path = _index_path()
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return
        for key, entry in raw.items():
            # Tolerate a hand-edited / truncated index the same way list_records
            # tolerates a corrupt record: skip the entry, never abort the load.
            if (isinstance(key, str) and isinstance(entry, list) and len(entry) == 3
                    and isinstance(entry[0], int) and isinstance(entry[1], int)
                    and isinstance(entry[2], dict)):
                _SUMMARY_CACHE[key] = (entry[0], entry[1], entry[2])
    except (OSError, ValueError, TypeError, RecursionError):
        # RecursionError: same class of gap as config.load_config -- a
        # pathologically deep index file must degrade like any other corrupt
        # cache (this is a cache, never data; see the docstring above).
        _SUMMARY_CACHE.clear()


def _save_index_locked() -> None:
    """Write the index back if it changed, dropping entries whose file is gone.
    Atomic replace; every failure is silent (this is a cache, not data)."""
    global _INDEX_DIRTY
    if not _INDEX_DIRTY:
        return
    _INDEX_DIRTY = False
    path = _index_path()
    if not path:
        return
    for key in [k for k in _SUMMARY_CACHE if not os.path.exists(k)]:
        del _SUMMARY_CACHE[key]
    payload = {k: [v[0], v[1], v[2]] for k, v in _SUMMARY_CACHE.items()}
    tmp = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tidx.", dir=os.path.dirname(path))
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise
        with f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except (OSError, ValueError):
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def invalidate_summary_cache(path: str | None = None) -> None:
    """Forget one cached summary, or all of them. Called after a record is
    deleted or pruned so a stale entry can never outlive its file."""
    global _INDEX_DIRTY
    with _SUMMARY_CACHE_LOCK:
        if path is None:
            _SUMMARY_CACHE.clear()
        else:
            _SUMMARY_CACHE.pop(os.path.abspath(path), None)
        _INDEX_DIRTY = True
        _save_index_locked()


def list_records(directory: str) -> list[dict]:
    """Return a newest-first summary list of saved sessions. Each entry carries
    enough metadata for the history list without loading every turn body."""
    global _INDEX_DIRTY
    out = []
    with _SUMMARY_CACHE_LOCK:
        _load_index_locked()
    for path in _iter_record_paths(directory):
        name = os.path.basename(path)
        key = os.path.abspath(path)
        try:
            st = os.stat(path)
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            continue
        with _SUMMARY_CACHE_LOCK:
            hit = _SUMMARY_CACHE.get(key)
        if hit is not None and (hit[0], hit[1]) == stamp:
            out.append(dict(hit[2]))
            continue
        try:
            rec = load_record(path)
        except (OSError, ValueError):
            continue
        # Tolerate a corrupted/hand-edited record: a non-list `turns` or a
        # null/non-numeric `started` must skip-or-coerce this one record, not
        # abort the whole History listing with a TypeError.
        turns = rec.get("turns", [])
        if not isinstance(turns, list):
            turns = []
        try:
            started = float(rec.get("started") or 0.0)
        except (TypeError, ValueError):
            started = 0.0
        first = turns[0] if turns and isinstance(turns[0], dict) else {}
        summary = {
            "file": name,
            "started": started,
            "started_iso": rec.get("started_iso", ""),
            "mode": rec.get("mode", ""),
            "target_in": rec.get("target_in", ""),
            "target_out": rec.get("target_out", ""),
            "turns": len(turns),
            # Prefer translation, but source-only recovery records must remain
            # visible and searchable in History too.
            "preview": ((first.get("text", "") or "")
                        or (first.get("src", "") or ""))[:80],
            "starred": bool(rec.get("starred", False)),
        }
        with _SUMMARY_CACHE_LOCK:
            _SUMMARY_CACHE[key] = (stamp[0], stamp[1], summary)
            _INDEX_DIRTY = True
        # Hand out a copy: callers (webui.list_sessions) merge and sort these,
        # and a mutation must never reach back into the cache.
        out.append(dict(summary))
    with _SUMMARY_CACHE_LOCK:
        _save_index_locked()          # no-op unless something was actually read
    out.sort(key=lambda r: r.get("started", 0.0), reverse=True)
    return out


def _cue_bounds(turns, idx):
    """Derive (start, end) seconds for cue `idx` from turn offsets."""
    start = float(turns[idx].get("t", 0.0))
    if idx + 1 < len(turns):
        nxt = float(turns[idx + 1].get("t", start + MIN_CUE_S))
        end = max(start + MIN_CUE_S, min(nxt, start + MAX_CUE_S))
        # Never overlap the following cue: when two turns start closer than
        # MIN_CUE_S, the floor above would push end past nxt. Clamp so cues stay
        # non-overlapping/monotonic (a short cue is better than a stacked one).
        if nxt > start:
            end = min(end, nxt)
    else:
        end = start + MIN_CUE_S
    return start, end


def _fmt_ts(seconds: float, *, vtt: bool) -> str:
    """Format a timestamp as SRT (HH:MM:SS,mmm) or VTT (HH:MM:SS.mmm)."""
    seconds = max(0.0, seconds)
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _multi_speaker(turns) -> bool:
    """True when the session saw more than one labeled speaker — the gate for
    rendering "S1:"/"S2:" prefixes (a single-voice transcript stays clean)."""
    labels = {t.get("spk") for t in turns
              if isinstance(t, dict) and t.get("spk") is not None}
    return len(labels) >= 2


def _two_way(turns) -> bool:
    """True when the record carries BOTH meeting directions — the gate for
    rendering the "who said it" prefix. A Video/Game record has no `leg` at all
    and must render exactly as it did before legs existed."""
    legs = {t.get("leg") for t in turns if isinstance(t, dict) and t.get("leg")}
    return len(legs) >= 2


def _spk_prefixes(turns, multi: bool, two_way: bool = False) -> list[str]:
    """Per-turn prefixes: the meeting direction, then "S1: " where the speaker
    changes.

    The speaker tag is emitted ONLY where the speaker changes from the previous
    labeled turn: one speaker talking across several consecutive turns reads as
    one labeled run, not a re-tagged line each time (owner feedback,
    2026-07-10). Same rule as the live captions and History.

    The direction tag, by contrast, is emitted on EVERY turn of a two-way
    record: in a meeting the two sides alternate constantly, and an omitted tag
    would read as "still the same side" exactly when it is not. Speaker labels
    come from the incoming capture only, so they never ride an outgoing turn."""
    out, prev = [], None
    for t in turns:
        spk = t.get("spk") if isinstance(t, dict) else None
        leg = t.get("leg") if isinstance(t, dict) else None
        pre = ""
        if two_way and leg:
            pre = (t_("leg_them") if leg == "incoming" else t_("leg_me")) + ": "
        if multi and spk is not None and spk != prev and leg != "outgoing":
            pre += f"S{int(spk)}: "
        out.append(pre)
        if spk is not None:
            prev = spk
    return out


CUE_WIDTH = 42          # the conventional subtitle line budget


def _wrap(line: str, width: int = CUE_WIDTH) -> str:
    """Fold one caption line to `width` on word boundaries.

    Players do not wrap for you: an unwrapped cue runs off the frame, and a
    simultaneous engine that never pauses long enough to split a turn produces
    very long ones (a field session rendered a single 548-character line).
    Nothing is ever dropped — an over-long cue becomes several lines rather
    than a truncated one — and a word longer than `width` is left intact
    instead of being broken mid-token."""
    words = line.split()
    if not words:
        return ""
    out, cur = [], words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            out.append(cur)
            cur = w
    out.append(cur)
    return "\n".join(out)


def _cue_text(turn, *, bilingual: bool, pre: str = "") -> str:
    """Caption body: translation, optionally with the source line above it.
    A speaker-change cue carries the tag on both lines. Each language line is
    wrapped independently so the two stay visually separate."""
    text = turn.get("text", "").strip()
    src = turn.get("src", "").strip()
    if bilingual and src:
        return _wrap(f"{pre}{src}") + (f"\n{_wrap(f'{pre}{text}')}" if text else "")
    # A bare prefix must not fabricate a cue for an empty turn.
    return _wrap(f"{pre}{text}") if text else ""


def _summary_header(record: dict) -> str:
    """Prefix block for a record's AI summary (see the 'summary' field docstring
    above), if it has one. TXT only — SRT/VTT are timed caption formats a prose
    summary has no cue to attach to."""
    summary = str(record.get("summary") or "").strip()
    return summary + "\n\n---\n\n" if summary else ""


def render_txt(record: dict, *, bilingual: bool = False) -> str:
    """Plain-text dump. Mono (default): one translation line per turn (parity with
    the legacy .txt export). Bilingual: each turn as its source line above the
    translation, turns separated by a blank line — for localization/dubbing work
    where both languages side by side beats a translated-only export."""
    turns = record.get("turns", [])
    pres = _spk_prefixes(turns, _multi_speaker(turns), _two_way(turns))
    header = _summary_header(record)
    if not bilingual:
        lines = [pres[i] + t.get("text", "").strip()
                 for i, t in enumerate(turns) if t.get("text", "").strip()]
        body = "\n".join(lines) + ("\n" if lines else "")
        return header + body if lines else body
    blocks = []
    for i, t in enumerate(turns):
        text = t.get("text", "").strip()
        src = t.get("src", "").strip()
        if not text and not src:
            continue
        pre = pres[i]
        if src and text:
            blocks.append(f"{pre}{src}\n{pre}{text}")
        else:
            blocks.append(pre + (src or text))
    body = "\n\n".join(blocks) + ("\n" if blocks else "")
    return header + body if blocks else body


def render_srt(record: dict, *, bilingual: bool = True) -> str:
    turns = record.get("turns", [])
    pres = _spk_prefixes(turns, _multi_speaker(turns), _two_way(turns))
    blocks = []
    for i, turn in enumerate(turns):
        body = _cue_text(turn, bilingual=bilingual, pre=pres[i])
        if not body:
            continue
        start, end = _cue_bounds(turns, i)
        blocks.append(
            f"{len(blocks) + 1}\n"
            f"{_fmt_ts(start, vtt=False)} --> {_fmt_ts(end, vtt=False)}\n"
            f"{body}\n"
        )
    return "\n".join(blocks)


def render_vtt(record: dict, *, bilingual: bool = True) -> str:
    turns = record.get("turns", [])
    pres = _spk_prefixes(turns, _multi_speaker(turns), _two_way(turns))
    blocks = ["WEBVTT\n"]
    for i, turn in enumerate(turns):
        body = _cue_text(turn, bilingual=bilingual, pre=pres[i])
        if not body:
            continue
        start, end = _cue_bounds(turns, i)
        blocks.append(
            f"{_fmt_ts(start, vtt=True)} --> {_fmt_ts(end, vtt=True)}\n"
            f"{body}\n"
        )
    return "\n".join(blocks)


_RENDERERS = {"txt": render_txt, "srt": render_srt, "vtt": render_vtt}


def export(record: dict, fmt: str, *, bilingual: bool = True) -> tuple[str, str]:
    """Render `record` to `fmt` ('txt'|'srt'|'vtt').

    `bilingual` keeps the source line alongside the translation (default) or, when
    False, emits a translated-only export. Returns (content, extension). Raises
    ValueError on an unknown format.
    """
    fmt = (fmt or "").lower()
    if fmt not in _RENDERERS:
        raise ValueError(f"unknown export format: {fmt!r}")
    return _RENDERERS[fmt](record, bilingual=bilingual), fmt


def _is_starred(entry_path: str) -> bool:
    """Best-effort peek at whether a transcript entry (session folder or legacy
    flat file) carries the starred flag, for prune_transcripts's exemption.
    Any failure (corrupt/unreadable/mid-write) reads as not-starred — a read
    error must never keep an old file from ever being pruned."""
    try:
        if os.path.isdir(entry_path):
            name = os.path.basename(entry_path)
            json_path = os.path.join(entry_path, name + ".json")
        else:
            json_path = entry_path
        with open(json_path, encoding="utf-8") as f:
            return bool(json.load(f).get("starred", False))
    except Exception:
        return False


def prune_transcripts(directory: str, max_age_days: int = 90, max_files: int = 500) -> int:
    """Housekeeping pass: cleans up transcripts older than `max_age_days` or exceeding
    `max_files` limit (keeps disk usage bounded). Fully guarded; returns pruned count.

    Starred sessions are exempt from BOTH budgets — they are simply never added
    to the pruning candidate list, so a user-marked session can never be swept
    away by age or by the 500-file cap."""
    if not directory or not os.path.exists(directory):
        return 0
    now = time.time()
    max_age_sec = max_age_days * 86400.0
    pruned = 0
    try:
        entries = []
        for name in os.listdir(directory):
            p = os.path.join(directory, name)
            if name.startswith("voxis_") and (os.path.isdir(p) or name.endswith(".json")):
                if _is_starred(p):
                    continue
                try:
                    mtime = os.path.getmtime(p)
                    entries.append((mtime, p))
                except OSError:
                    pass
        entries.sort(key=lambda x: x[0])
        remaining = []
        for mtime, p in entries:
            if now - mtime > max_age_sec:
                try:
                    if os.path.isdir(p):
                        import shutil
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                    pruned += 1
                except Exception:
                    remaining.append((mtime, p))
            else:
                remaining.append((mtime, p))

        if len(remaining) > max_files:
            to_remove = remaining[: len(remaining) - max_files]
            for _, p in to_remove:
                try:
                    if os.path.isdir(p):
                        import shutil
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                    pruned += 1
                except Exception:
                    pass
    except Exception:
        pass
    if pruned:
        # Summaries are keyed by path; pruned files will simply never be yielded
        # again, so their entries would linger for the process lifetime. Cheap to
        # drop them wholesale — the next listing repopulates from stat + disk.
        invalidate_summary_cache()
    return pruned

