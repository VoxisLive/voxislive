"""OutgoingPipeline gets the same WSOLA catch-up stager the incoming leg has
had since PR #39 (Faz 1 of the own-voice-outgoing roadmap item, see
.vault/meeting-own-voice-warmup-clone-2026-08-07 / the Tier-1 backlog plan).
A long outgoing turn can be generated faster than realtime just like the
incoming one, so it needs the same backlog-bounding; the CHOICE this makes is
that the optional confidence monitor stays on the raw, unpaced feed — it
exists to answer "what does the other party hear", and the mic side (which
the stager paces) is what actually reaches them.
"""
from typing import ClassVar

import pytest

from app import pipeline as P


class _Stub:
    """Swallows whatever the constructor wants; records nothing."""

    def __init__(self, *a, **kw):
        self.rate = 16000

    def __getattr__(self, name):
        return lambda *a, **kw: None


class _FakePlayer:
    def __init__(self, *a, **kw):
        self.rate = 24000
        self.fed = []

    def feed_tts_pcm16(self, data):
        self.fed.append(data)

    def stop(self):
        pass


class _FakeStager:
    """Records construction + every call. `instances` is class-level because
    the pipeline builds the stager internally — tests recover it via
    `pipe._stager` (the instance itself), this list is just for bookkeeping
    across a fixture's several builds within one test."""
    instances: ClassVar[list] = []

    def __init__(self, player, on_status=None, input_rate=24000):
        self.player = player
        self.input_rate = input_rate
        self.fed = []
        self.cleared = 0
        self.stopped = False
        _FakeStager.instances.append(self)

    def feed(self, data):
        self.fed.append(data)

    def clear(self):
        self.cleared += 1

    def stop(self):
        self.stopped = True


@pytest.fixture
def built(monkeypatch):
    """Constructs a real OutgoingPipeline with the audio layer stubbed out
    (Player replaced by a fake that records fed PCM instead of a swallow-all
    stub, so feed routing is actually observable) and returns the pipe."""
    _FakeStager.instances.clear()

    def _fake_make(cfg, target, **kw):
        return _Stub()

    monkeypatch.setattr(P, "make_translator", _fake_make)
    monkeypatch.setattr(P, "Player", _FakePlayer)
    monkeypatch.setattr(P, "Capture", _Stub)
    monkeypatch.setattr(P, "find_device", lambda *a, **kw: None)
    monkeypatch.setattr(P.sysaudio, "make_virtual_mic", lambda: None)
    monkeypatch.setattr(P.sysaudio, "snapshot_own_audio_streams", list)
    monkeypatch.setattr(P, "_GatedSource", _Stub)
    monkeypatch.setattr(P, "AdaptivePlaybackStager", _FakeStager)

    def _build(cfg, engine="qwen"):
        return P.OutgoingPipeline(
            cfg, lambda target: (engine, "key", "model", None),
            lambda *a: None, lambda *a: None)

    return _build


def _cfg(**kw):
    base = {"devices": {"microphone": "", "meeting_mic_playback": "",
                        "headphones_output": ""},
            "target_language_outgoing": "en",
            "target_language_incoming": "tr"}
    base.update(kw)
    return base


def test_qwen_routed_leg_gets_a_stager(built):
    pipe = built(_cfg(), engine="qwen")
    assert isinstance(pipe._stager, _FakeStager)
    assert pipe._stager.player is pipe.player


def test_gemini_routed_leg_gets_a_stager(built):
    pipe = built(_cfg(), engine="gemini")
    assert isinstance(pipe._stager, _FakeStager)


def test_cascade_routed_leg_has_no_stager(built):
    # Cascade paces its own local synthesis (same reasoning as the incoming
    # leg — see IncomingPipeline.__init__).
    pipe = built(_cfg(), engine="cascade")
    assert pipe._stager is None


def test_feed_translated_audio_routes_through_the_stager(built):
    pipe = built(_cfg(), engine="qwen")
    pipe._feed_translated_audio(b"abc")
    assert pipe._stager.fed == [b"abc"]
    assert pipe.player.fed == []          # the stager owns the mic side now


def test_feed_translated_audio_falls_back_to_direct_feed_without_a_stager(built):
    pipe = built(_cfg(), engine="cascade")
    pipe._feed_translated_audio(b"abc")
    assert pipe.player.fed == [b"abc"]


def test_monitor_always_gets_the_raw_unpaced_feed(built):
    # The monitor answers "what does the other party hear" — it must mirror
    # the raw data even while the mic side is paced through the stager,
    # never a second independently-timed copy through the stager itself.
    pipe = built(_cfg(monitor_outgoing_translation=True), engine="qwen")
    monitor = _FakePlayer()
    pipe.monitor_player = monitor
    pipe._feed_translated_audio(b"xyz")
    assert pipe._stager.fed == [b"xyz"]
    assert monitor.fed == [b"xyz"]


def test_stop_all_stops_the_outgoing_stager(built):
    pipe = built(_cfg(), engine="qwen")
    stager = pipe._stager
    P._stop_all(pipe)
    assert stager.stopped is True


def test_swap_to_gemini_clears_the_outgoing_stager(built, monkeypatch):
    pipe = built(_cfg(), engine="qwen")
    stager = pipe._stager
    assert stager is not None

    def _resolve(target, force_gemini=False):
        return ("gemini", "key2", "model2", None)

    pipe._resolve = _resolve
    monkeypatch.setattr(P, "make_translator", lambda *a, **kw: _Stub())
    ok = P._swap_to_gemini(pipe, "target_language_outgoing", "Outgoing", RuntimeError("x"))
    assert ok is True
    assert stager.cleared == 1
    # The worker stays alive for the replacement stream (same contract as the
    # incoming leg) — clear() drops pending audio, it does not stop().
    assert stager.stopped is False
