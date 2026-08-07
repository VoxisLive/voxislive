"""Meeting mode keeps its two directions apart.

A meeting runs TWO translators — incoming (other party -> user) and outgoing
(user -> other party) — and both feed the same caption callback. Before this,
`ModeController._build` handed each pipeline the identical `on_text` and
`Bridge._on_text` kept one set of buffers, so the two translations interleaved
inside a single caption line and landed in the transcript indistinguishable
from each other. The lock around _on_text kept the buffers from corrupting; it
could not keep the two CONVERSATIONS apart (session audit 2026-07-28).

Video/Game mode must be completely unaffected: no `leg` in the record, no
direction prefix in any export.
"""
import threading

import app.transcript_store as ts
import app.webui as webui
from app.webui import LINE_GAP, Bridge


def _bridge(mode="meeting"):
    b = object.__new__(Bridge)
    b._legs = {"incoming": webui._LegState(), "outgoing": webui._LegState()}
    b._text_lock = threading.RLock()
    b._src_track = []
    b._audio_track = []
    b._session_start = 0.0
    b._lines = []
    b._turns = []
    b._overlay_text = ""
    b._overlay_until = 0.0
    b._cur_spk = None
    b._spk_seen = set()
    b._events_seen = []
    b._put_event = lambda ev: b._events_seen.append(ev)
    b._obs_write = lambda *a, **k: None
    b.controller = type("C", (), {"current_playback_backlog": lambda self: 0.0,
                                  "mode": mode})()
    return b


def _feed(b, direction, text, t, leg="incoming"):
    orig = webui.time.time
    webui.time.time = lambda: t
    try:
        b._on_text_locked(direction, text, leg)
    finally:
        webui.time.time = orig


def test_two_directions_do_not_share_a_caption_line():
    """The core defect: without per-leg state the outgoing translation appends
    into the incoming caption line and the record cannot tell them apart."""
    b = _bridge()
    _feed(b, "out", "Bu ceyrek icin hedefimiz ne?", 0.1, "incoming")
    _feed(b, "out", "What is our target for this quarter?", 0.2, "outgoing")
    _feed(b, "out", " Uc yeni pazara giriyoruz.", 0.3 + LINE_GAP, "incoming")
    b._flush_turns()

    got = [(t["leg"], t["text"]) for t in b._turns]
    assert got == [
        ("incoming", "Bu ceyrek icin hedefimiz ne?"),
        ("outgoing", "What is our target for this quarter?"),
        ("incoming", "Uc yeni pazara giriyoruz."),
    ]
    # Neither side's words leaked into the other's line.
    assert all("target" not in txt for side, txt in got if side == "incoming")


def test_turns_stay_in_one_chronological_timeline():
    b = _bridge()
    _feed(b, "out", "bir", 1.0, "incoming")
    _feed(b, "out", "one", 2.0, "outgoing")
    _feed(b, "out", "iki", 3.0 + LINE_GAP, "incoming")
    b._flush_turns()
    times = [t["t"] for t in b._turns]
    assert times == sorted(times)


def test_each_leg_gets_its_own_source_pairing():
    """The user's own mic ASR must never be offered to the other party's
    translation turn, and vice versa."""
    b = _bridge()
    _feed(b, "in", "What is our target?", 0.0, "outgoing")
    _feed(b, "in", "Hedefimiz ne?", 0.0, "incoming")
    _feed(b, "out", "Hedefimiz ne diye soruyor.", 4.0, "incoming")
    _feed(b, "out", "What is our target?", 4.0, "outgoing")
    b._flush_turns()
    by_leg = {t["leg"]: t["src"] for t in b._turns}
    assert by_leg["incoming"] == "Hedefimiz ne?"
    assert by_leg["outgoing"] == "What is our target?"


def test_speaker_labels_never_ride_the_outgoing_leg():
    """The tracker only listens to the incoming capture — the user is one known
    voice, so tagging their turns "S2" would be a fabrication."""
    b = _bridge()
    b._spk_seen = {1, 2}
    b._cur_spk = 2
    _feed(b, "in", "Hello there.", 0.0, "incoming")
    _feed(b, "in", "Merhaba.", 0.0, "outgoing")
    _feed(b, "out", "Merhaba oradaki.", 4.0, "incoming")
    _feed(b, "out", "Hello there.", 4.0, "outgoing")
    b._flush_turns()
    for turn in b._turns:
        if turn["leg"] == "outgoing":
            assert "spk" not in turn


def test_only_the_incoming_leg_drives_the_overlay():
    """The overlay and the OBS file are single-line surfaces: the user needs the
    OTHER party read back to them, not their own words."""
    b = _bridge()
    _feed(b, "out", "Karsi taraf konusuyor.", 0.1, "incoming")
    assert "Karsi taraf" in b._overlay_text
    _feed(b, "out", "My own words.", 0.2, "outgoing")
    assert "My own words" not in b._overlay_text


def test_caption_event_carries_the_leg():
    b = _bridge()
    _feed(b, "out", "merhaba", 0.1, "outgoing")
    trans = [e for e in b._events_seen if e[0] == "trans"]
    assert trans and trans[-1][5] == "outgoing"


def test_video_mode_record_has_no_leg_at_all():
    """A Video/Game record must serialize exactly as it did before legs
    existed — no new key, no direction prefix in any export."""
    b = _bridge(mode="video")
    _feed(b, "out", "Tek yonlu ceviri.", 0.1)
    b._flush_turns()
    assert all("leg" not in t for t in b._turns)
    rec = ts.build_record(0.0, b._turns)
    assert all("leg" not in t for t in rec["turns"])
    assert ts.render_txt(rec).strip() == "Tek yonlu ceviri."


def test_exports_label_both_sides_of_a_meeting():
    turns = [
        {"t": 0.0, "dir": "out", "src": "", "text": "Hedefimiz ne?", "leg": "incoming"},
        {"t": 2.0, "dir": "out", "src": "", "text": "What is our target?", "leg": "outgoing"},
    ]
    rec = ts.build_record(0.0, turns, mode="meeting")
    assert [t["leg"] for t in rec["turns"]] == ["incoming", "outgoing"]
    from app.i18n import t as _t
    txt = ts.render_txt(rec)
    assert f"{_t('leg_them')}: Hedefimiz ne?" in txt
    assert f"{_t('leg_me')}: What is our target?" in txt
    # And the same prefixes reach the subtitle exports.
    assert _t("leg_me") in ts.render_srt(rec)


def test_one_sided_meeting_is_not_labelled():
    """Listen-only (no virtual mic) produces a single direction — labelling it
    would imply a second side that never spoke."""
    turns = [{"t": 0.0, "dir": "out", "src": "", "text": "Sadece dinliyoruz.",
              "leg": "incoming"}]
    rec = ts.build_record(0.0, turns, mode="meeting")
    from app.i18n import t as _t
    assert _t("leg_them") not in ts.render_txt(rec)


def test_mode_controller_binds_a_leg_to_each_pipeline():
    """The sink each pipeline receives must already know its side."""
    from app.pipeline import ModeController
    mc = object.__new__(ModeController)
    seen = []
    mc.on_text = lambda direction, text, leg=None: seen.append((direction, text, leg))
    mc._text_sink("incoming")("out", "a")
    mc._text_sink("outgoing")("out", "b")
    assert seen == [("out", "a", "incoming"), ("out", "b", "outgoing")]


def test_text_sink_tolerates_a_two_argument_consumer():
    """Older/stub consumers that predate the leg argument must not break."""
    from app.pipeline import ModeController
    mc = object.__new__(ModeController)
    seen = []
    mc.on_text = lambda direction, text: seen.append((direction, text))
    mc._text_sink("outgoing")("out", "a")
    assert seen == [("out", "a")]
