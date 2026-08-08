"""Bridge source<->translation pairing + save-flush robustness.

Regression coverage for the Qwen-beta transcript bugs Ivo reported on 1.0.26:
  * the JSON `src` field repeated the first source segment in every turn, and
  * a session whose translation stream dropped out reported "nothing to save".

Both stem from the transcript recorder coupling turn boundaries to LINE_GAP
timing gaps that Gemini's paused source stream produces but Qwen's continuous,
cumulative ASR does not.
"""
import threading

import app.webui as webui
from app.history_bridge import _strip_inline_repeat
from app.webui import LINE_GAP, SRC_LAG_S, Bridge


def _bare_bridge():
    """A Bridge with only the transcript buffers wired up — no ModeController,
    no window — so the pure text-pairing logic can be driven directly."""
    b = object.__new__(Bridge)
    # Per-direction accumulators (webui._LegState); a bare Bridge skips __init__.
    b._legs = {"incoming": webui._LegState(), "outgoing": webui._LegState()}
    b._text_lock = threading.RLock()
    b._src_track = []
    b._audio_track = []
    b._session_start = 0.0
    b._lines = []
    b._turns = []
    b._overlay_text = ""
    b._overlay_until = 0.0
    # Speaker-labeling state (see Bridge.__init__).
    b._cur_spk = None
    b._spk_seen = set()
    b._put_event = lambda *a, **k: None      # swallow UI events
    b._obs_write = lambda *a, **k: None       # swallow OBS file writes
    # No live session/stager off this bare Bridge — backlog is always 0.
    b.controller = type("C", (), {"current_playback_backlog": lambda self: 0.0})()
    return b


def _feed(b, direction, text, t, leg="incoming"):
    """Drive _on_text_locked with a controlled monotonic clock so LINE_GAP
    boundaries are deterministic (no reliance on wall-clock spacing)."""
    orig = webui.time.time
    webui.time.time = lambda: t
    try:
        b._on_text_locked(direction, text, leg)
    finally:
        webui.time.time = orig


def test_continuous_source_does_not_leak_into_earlier_turn():
    """Qwen streams source ASR continuously (no LINE_GAP pause) — the source
    stream alone gives no per-turn boundary, and translation trails it by the
    model's simultaneous-interpretation lag (SRC_LAG_S). Each translation
    turn claims only the source heard by (now - SRC_LAG_S) at the moment it
    finalizes, leaving anything heard more recently than that queued for a
    LATER turn instead of leaking into this one. Words that arrive after a
    turn's cutoff but before that turn is popped must NOT appear in that
    turn's src (the bug this replaced: grabbing "everything buffered right
    now" over-claimed into whichever turn finished first)."""
    b = _bare_bridge()
    # Continuous source, one word every second, never pausing >LINE_GAP —
    # nothing ever rolls into _src_done; it all stays live in _src_buf.
    for i, w in enumerate(["Uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho"]):
        _feed(b, "in", w + " ", float(i))
    # Turn 1 opens (no pop yet — first output of the session).
    _feed(b, "out", "T1.", 8.0)
    # More source keeps arriving WHILE turn 1 is the current line — this must
    # end up on a later turn, not turn 1, even though it's already in
    # _src_buf by the time turn 1's pop runs.
    _feed(b, "in", "nueve ", 9.0)
    _feed(b, "in", "diez ", 10.0)
    # Turn 1 finalizes (output pause) — cutoff = 10.6 - SRC_LAG_S.
    _feed(b, "out", "T2.", 10.6)
    assert 10.6 - SRC_LAG_S < 9.0, "test assumes cutoff lands before 'nueve'"
    # Turn 2 finalizes, now well past the cutoff for the remaining words.
    _feed(b, "out", "T3.", 10.6 + 0.1 + LINE_GAP)
    b._flush_turns()

    texts = [t["text"] for t in b._turns]
    srcs = [t["src"] for t in b._turns]
    assert texts == ["T1.", "T2.", "T3."]
    # Turn 1 claims only what had been heard well before it finalized —
    # "nueve"/"diez" (heard after turn 1's cutoff) are NOT in it.
    assert srcs[0] == "Uno dos tres cuatro cinco seis siete ocho"
    assert "nueve" not in srcs[0] and "diez" not in srcs[0]
    # They land on turn 2 instead — nothing dropped, nothing duplicated.
    assert srcs[1] == "nueve diez"
    assert srcs[2] is None


def test_gemini_paused_source_still_pairs_per_turn():
    """Gemini's source stream pauses (>LINE_GAP) between utterances, rolling
    _cur_src into _last_src. That path must keep pairing correctly after the fix."""
    b = _bare_bridge()
    _feed(b, "in", "Hello there.", 0.0)
    _feed(b, "out", "Merhaba oradaki.", 0.1)
    # A real speech pause: next source arrives >LINE_GAP later, so it rolls over.
    _feed(b, "in", "How are you?", 5.0)
    _feed(b, "out", "Nasilsin?", 5.1 + LINE_GAP)
    b._flush_turns()

    srcs = [t["src"] for t in b._turns]
    texts = [t["text"] for t in b._turns]
    assert texts == ["Merhaba oradaki.", "Nasilsin?"]
    assert srcs[0] == "Hello there."
    assert srcs[1] == "How are you?"


def test_two_sources_complete_before_one_turn_keep_both():
    """Two source utterances both pause-complete (>LINE_GAP) before a single
    translation turn finalizes. The old single-slot _last_src overwrote the first
    with the second, so its JSON `src` was lost and later turns went blank (the
    Gemini-on-a-movie regression Ivo reported on 1.0.27). The FIFO must preserve
    both and hand them to their turns in order — neither src is ever empty."""
    b = _bare_bridge()
    # Two speakers, each source separated by a real >LINE_GAP pause, BEFORE the
    # (lagging) translations for either arrive.
    _feed(b, "in", "Alice speaks.", 0.0)
    _feed(b, "in", "Bob replies.", 5.0)          # >LINE_GAP after Alice -> queued
    _feed(b, "in", "Alice again.", 10.0)         # >LINE_GAP after Bob   -> queued
    # Now the three translation turns finalize, each opening after a LINE_GAP gap.
    _feed(b, "out", "T-Alice.", 11.0)
    _feed(b, "out", "T-Bob.", 11.1 + LINE_GAP)
    _feed(b, "out", "T-Alice2.", 11.2 + 2 * LINE_GAP)
    b._flush_turns()

    srcs = [t["src"] for t in b._turns]
    texts = [t["text"] for t in b._turns]
    assert texts == ["T-Alice.", "T-Bob.", "T-Alice2."]
    # Every turn carries a non-empty, correctly-ordered source — no overwrite, no
    # blank src.
    assert "" not in srcs
    assert srcs == ["Alice speaks.", "Bob replies.", "Alice again."]


def test_flush_saves_source_when_translation_stream_dropped():
    """If Qwen drops its translation text entirely but source ASR arrived, the
    session must still be saveable (source-only turn) rather than "nothing to save"."""
    b = _bare_bridge()
    _feed(b, "in", "Source only, no translation came back.", 0.0)
    assert b._turns == []          # nothing folded yet
    b._flush_turns()
    assert len(b._turns) == 1
    assert b._turns[0]["src"] == "Source only, no translation came back."
    assert b._turns[0]["text"] == ""


def test_flush_does_not_add_spurious_source_only_turn_to_normal_session():
    """A normal session with real translation must NOT get an extra empty-text
    source-only turn appended when a residual source tail lingers at stop."""
    b = _bare_bridge()
    _feed(b, "in", "One.", 0.0)
    _feed(b, "out", "Bir.", 0.1)
    # Residual source arrives after the translation turn (its translation is still
    # "in flight" at stop) — must not become a bogus trailing turn.
    _feed(b, "in", "Two.", 5.0)
    b._flush_turns()
    # Only the real translation turn is recorded.
    assert [t["text"] for t in b._turns] == ["Bir."]


def test_empty_session_saves_nothing():
    b = _bare_bridge()
    b._flush_turns()
    assert b._turns == []


def test_opt_in_problem_report_keeps_source_only_recovery_text():
    b = _bare_bridge()
    b._turns = [{"src": "Recovered source", "text": ""}]
    assert b._collect_transcript() == "Recovered source"


# --- turn-length safety valves ----------------------------------------------

def test_continuous_stream_splits_at_a_sentence_end():
    """LINE_GAP alone assumes the engine pauses between utterances. A
    simultaneous engine that streams continuously never gives it that pause, so
    one turn swallowed 20+ seconds of speech and rendered a 548-character
    caption line (session audit 2026-07-28). Past MAX_LINE_CHARS the stream must
    split — at a sentence end, not mid-clause."""
    b = _bare_bridge()
    b._session_start = 0.0
    # Distinct sentences: identical ones would trip the re-speak guard instead
    # and mask what this test is about.
    sentences = [f"Bu {i} numarali cumle yeterince uzunlukta yazilmistir. "
                 for i in range(8)]
    tick = 0.0
    # Feed continuously: every increment lands well inside LINE_GAP.
    for s in sentences:
        tick += 0.2
        _feed(b, "out", s, tick)
    b._flush_turns()
    texts = [t["text"] for t in b._turns]
    assert len(texts) > 1, "a continuous stream must still produce several turns"
    assert all(len(x) <= webui.HARD_LINE_CHARS for x in texts)
    # Every split landed on a sentence boundary — no clause was cut in half.
    assert all(x.rstrip().endswith(webui.SENTENCE_END) for x in texts)
    # Nothing was lost or duplicated in the split.
    assert " ".join(texts).split() == "".join(sentences).split()


def test_normal_length_turns_are_not_split():
    """The valves must only catch pathological turns; an ordinary utterance
    (~88 chars in the measured session) keeps its existing boundaries."""
    b = _bare_bridge()
    b._session_start = 0.0
    _feed(b, "out", "Kisa bir cumle.", 0.1)
    _feed(b, "out", " Devami da kisa.", 0.3)
    b._flush_turns()
    assert [t["text"] for t in b._turns] == ["Kisa bir cumle. Devami da kisa."]


def test_run_on_without_punctuation_still_hits_a_hard_ceiling():
    b = _bare_bridge()
    b._session_start = 0.0
    tick = 0.0
    for i in range(12):
        tick += 0.2
        _feed(b, "out", f"kelime{i} " * 10, tick)
    b._flush_turns()
    assert all(len(t["text"]) <= webui.HARD_LINE_CHARS + 80 for t in b._turns)
    assert len(b._turns) > 1


# --- engine re-speak guard --------------------------------------------------

def test_reworded_respeak_is_dropped():
    """The re-speak after an internal reconnect is REGENERATED, so it comes back
    lightly reworded. Exact equality let it through as a second turn that was
    never spoken aloud (field session t=653 vs t=662)."""
    line = "rezidans temel olarak 10 haftalik yogun yuz yuze bir programdir"
    b = _bare_bridge()
    b._session_start = 0.0
    _feed(b, "out", line, 0.1)
    _feed(b, "out", "Yani, " + line, 0.2 + webui.LINE_GAP)
    b._flush_turns()
    assert [t["text"] for t in b._turns] == [line]


def test_genuine_repetition_of_a_short_line_is_kept():
    """Short repeats are plausible dialogue and must survive the streaming
    guard. (The stop-time tail guard drops an exact trailing repeat outright —
    long-standing behaviour — so the repeat is checked mid-stream, not as the
    session's last line.)"""
    b = _bare_bridge()
    b._session_start = 0.0
    _feed(b, "out", "Evet.", 0.1)
    _feed(b, "out", "Evet.", 0.2 + webui.LINE_GAP)
    _feed(b, "out", "Devam edelim.", 0.3 + 2 * webui.LINE_GAP)
    b._flush_turns()
    assert [t["text"] for t in b._turns] == ["Evet.", "Evet.", "Devam edelim."]


def test_different_long_sentences_are_both_kept():
    a = "Rezidans on hafta surer ve tamamen yuz yuze yapilir burada."
    c = "Yatirim komitesi onuncu haftada sanal olarak toplanacaktir."
    b = _bare_bridge()
    b._session_start = 0.0
    _feed(b, "out", a, 0.1)
    _feed(b, "out", c, 0.2 + webui.LINE_GAP)
    b._flush_turns()
    assert [t["text"] for t in b._turns] == [a, c]


# --- source arrival track ----------------------------------------------------

def test_source_track_captures_arrival_times():
    """Recorded independently of the per-turn pairing, so the pairing can be
    checked against it later."""
    b = _bare_bridge()
    b._session_start = 100.0
    _feed(b, "in", "Hello ", 101.0)
    _feed(b, "in", "there.", 101.2)      # same breath — merged into one entry
    _feed(b, "in", "Second.", 110.0)     # a real gap — its own entry
    assert [(round(e["t"], 1), e["text"]) for e in b._src_track] == [
        (1.0, "Hello there."), (10.0, "Second."),
    ]


def test_source_track_separates_the_meeting_legs():
    b = _bare_bridge()
    # Non-zero: _session_start doubles as the "is a session running" sentinel
    # everywhere in the Bridge, so 0.0 reads as "no session" and records nothing.
    b._session_start = 100.0
    _feed(b, "in", "Karsi taraf.", 101.0)
    _feed(b, "in", "Benim sesim.", 101.0, leg="outgoing")
    legs = [e.get("leg") for e in b._src_track]
    assert legs == [None, "outgoing"]


def test_source_track_is_bounded():
    b = _bare_bridge()
    b._session_start = 100.0
    for i in range(b.SRC_TRACK_MAX + 50):
        _feed(b, "in", f"w{i}", 101.0 + i * 2.0)   # each past the merge window
    assert len(b._src_track) == b.SRC_TRACK_MAX


# --- translated-audio track --------------------------------------------------

def test_audio_track_samples_produced_speech():
    b = _bare_bridge()
    b._session_start = 100.0
    produced = {"s": 0.0}
    b.controller = type("C", (), {
        "current_playback_backlog": lambda self: 0.0,
        "translated_audio_seconds": lambda self: produced["s"],
        "mode": "video"})()
    _feed(b, "out", "bir", 101.0)
    produced["s"] = 4.0
    _feed(b, "out", "iki", 105.0)          # past the merge window
    assert [(round(e["t"], 1), e["sec"]) for e in b._audio_track] == [(1.0, 0.0), (5.0, 4.0)]


def test_audio_track_survives_a_controller_without_the_counter():
    """Instrumentation must never break a session: an older/stub controller just
    yields no samples."""
    b = _bare_bridge()
    b._session_start = 100.0
    _feed(b, "out", "bir", 101.0)
    assert b._audio_track == []


# --- engine re-speak INSIDE one caption line ---------------------------------

def test_inline_respeak_is_removed_keeping_the_tail():
    """Field shape (identical in two runs of the same video, 2026-07-29): the
    engine emits a full clause twice inside ONE line, with a connective between.
    The audio says it once — only the caption carries it twice. Whatever follows
    the second copy is real speech and must survive."""
    line = ("Ve daha fazlasi icin Leo English Podcast'e abone olmayi unutmayin. "
            "Tamam, Ve daha fazlasi icin Leo English Podcast'e abone olmayi "
            "unutmayin. pratik Ingilizce dersleri.")
    out = _strip_inline_repeat(line)
    assert out.count("abone olmayi unutmayin") == 1
    assert out.endswith("pratik Ingilizce dersleri."), "tail must not be eaten"


def test_inline_respeak_never_drops_a_word_of_the_tail():
    """A fuzzy match may run one word past the real repeat; that word would be
    something the speaker actually said."""
    line = "bir iki uc dort bes alti X bir iki uc dort bes alti YENI kelime"
    out = _strip_inline_repeat(line)
    assert out.split()[-2:] == ["YENI", "kelime"]


def test_short_repetition_is_left_alone():
    """"Evet. Evet." is dialogue, not an artifact."""
    for line in ("Evet. Evet.", "Tamam, tamam.", "Konusmaya devam et. Konusmaya devam et."):
        assert _strip_inline_repeat(line) == line


def test_ordinary_line_is_untouched():
    line = "Bugun hava cok guzel ve yarin da guzel olacak diye dusunuyorum."
    assert _strip_inline_repeat(line) == line


def test_repaired_text_is_always_a_subsequence():
    """The repair may only DELETE — never reorder or invent."""
    line = ("aaa bbb ccc ddd eee fff ggg hhh "
            "aaa bbb ccc ddd eee fff ggg hhh son kelime")
    out = _strip_inline_repeat(line).split()
    it = iter(line.split())
    assert all(tok in it for tok in out)


def test_finalized_turn_is_repaired():
    b = _bare_bridge()
    b._session_start = 100.0
    dup = ("bugun daha sakin hissetmenize yardimci olmak istiyoruz daha net "
           "yani bugun daha sakin hissetmenize yardimci olmak istiyoruz daha net")
    _feed(b, "out", dup, 101.0)
    b._flush_turns()
    text = b._turns[0]["text"]
    assert text.count("sakin hissetmenize") == 1
