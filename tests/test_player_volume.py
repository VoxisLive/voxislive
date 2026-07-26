"""The translation-volume slider must be LINEAR: tts_gain applied exactly once.

It used to be applied twice -- once in Player.feed_tts_pcm16 on the way into the
ring, and again in the output callback via _mix_to_stereo -> place_center. The
slider was therefore squared: 50% played at 25% (-12 dB instead of -6), and 150%
asked for 2.25x, which the 0.97 limiter simply crushed, so the top half of the
slider added distortion rather than level.
"""
import threading

import numpy as np

from app.audio_io import Player, _Ring, _mix_to_stereo


def _bare_player(gain: float) -> Player:
    """A Player with only what feed_tts_pcm16 touches -- no PortAudio stream."""
    p = Player.__new__(Player)
    p._tts_lock = threading.Lock()
    p._tts_rem = b""
    p._tts_enhance = None
    p._tts_in_rate = 24000
    p._tts_resample = lambda x: x          # rate-matched: identity
    p.tts_gain = gain
    p.tts = _Ring(2.0, 24000, channels=1, drop_newest=True)
    return p


def _feed_then_mix(gain: float, sample: float) -> float:
    """One full-scale-ish sample through the real path: feed -> ring -> callback
    mix. Returns the amplitude that would reach the limiter."""
    p = _bare_player(gain)
    pcm = np.array([int(sample * 32767)], dtype="<i2").tobytes()
    p.feed_tts_pcm16(pcm)
    tts_mono = p.tts.pull(1).reshape(-1)
    stereo = _mix_to_stereo(tts_mono, np.zeros((1, 2), dtype=np.float32),
                            p.tts_gain, 1.25, False)
    return float(stereo[0, 0])


def test_gain_is_applied_exactly_once():
    for gain, expected in ((0.5, 0.5), (0.7, 0.7), (1.0, 1.0), (1.5, 1.5)):
        got = _feed_then_mix(gain, 1.0)
        assert abs(got - expected) < 1e-3, (
            f"slider {gain:.0%} produced {got:.3f}, expected {expected:.3f} "
            "(gain applied twice?)")


def test_ring_holds_ungained_audio_so_a_slider_move_applies_to_it():
    """Gain lives only in the callback, so moving the slider changes audio that
    is ALREADY queued -- the level cannot step mid-utterance."""
    p = _bare_player(0.5)
    p.feed_tts_pcm16(np.array([16384], dtype="<i2").tobytes())
    queued = float(p.tts.pull(1).reshape(-1)[0])
    assert abs(queued - 0.5) < 1e-3, "ring must hold the raw sample, not a scaled one"


def test_halving_the_slider_halves_the_output():
    """The property the squared curve broke: output is proportional to gain."""
    full = _feed_then_mix(1.0, 0.8)
    half = _feed_then_mix(0.5, 0.8)
    assert abs(half - full / 2.0) < 1e-3


def test_health_watcher_thread_stops_with_the_player():
    """_watch_ring_health used to be `while True`, leaking one thread (holding a
    reference to its dead Player's ring) per session start."""
    p = Player.__new__(Player)
    p.tts = _Ring(1.0, 24000, channels=1)
    p._health_stop = threading.Event()
    p._watch_ring_health()
    def names():
        return [t.name for t in threading.enumerate()]
    assert "tts-ring-health" in names()
    p._health_stop.set()
    for t in threading.enumerate():
        if t.name == "tts-ring-health":
            t.join(timeout=3.0)
    assert "tts-ring-health" not in names()
