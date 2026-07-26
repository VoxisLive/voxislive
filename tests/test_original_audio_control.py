"""The "original audio" control (mode + duck level) must reach the mixer.

Field report 2026-07-25, round 1: moving the original-volume slider did
nothing. Cause: on the VB-CABLE capture path the mid-gain computation lived
inside `on_chunk`'s NON-premium `else` branch, so a machine that resolved to
vbcable + premium (ADRess vocal split) never assigned player.mid_gain at all --
it stayed at the 1.0 default and both `original_audio` and `duck_gain` were
inert. The driverless path was unaffected (it steers the session ducker
directly, in `on_loop`).

Round 2, same day: the round-1 fix routed the premium level onto a new
`player.ambient_gain`, scaling the WHOLE ambient bed (mid AND side) uniformly
-- on the theory that ADRess's own fixed -18 dB floor already handled the
speaker, so the slider's only remaining job was ambience. That inverted the
control: it ducked the music (which VB-CABLE + ADRess exists specifically to
preserve) while the speaker stayed at ADRess's fixed floor, un-adjustable by
the user. Corrected: the level now feeds ADRess's own per-bin centre floor
directly (`execute_vocal_split(..., level=)`), so the slider ducks the SPEAKER;
the mixer's `mid_gain` is left at 1.0 on the premium path and the sides are
never touched by this control at all.

These drive the REAL IncomingPipeline._apply_original_gain, not a copy of it --
that method was extracted from the closure precisely so it could be tested
without opening audio devices.
"""
import pytest

from app.pipeline import IncomingPipeline, ModeController


class _Player:
    def __init__(self):
        self.mid_gain = 1.0
        self.tts_active = False


def _pipe(original_mode="duck", duck_gain=0.3, premium=False):
    p = IncomingPipeline.__new__(IncomingPipeline)
    p.player = _Player()
    p._speak = 0.0
    p._original_mode = original_mode
    p._duck_gain = duck_gain
    p._use_premium = premium
    return p


def _settle(p, speaking=True, n=60):
    """Run enough blocks for the ~80 ms _speak ramp to converge, and return the
    gain this path actually steers (see _apply_original_gain)."""
    for _ in range(n):
        level = p._apply_original_gain(speaking)
    return level


@pytest.mark.parametrize("premium", [False, True])
def test_duck_gain_reaches_the_mixer(premium):
    """THE regression: on the premium path neither gain was assigned at all."""
    p = _pipe(original_mode="duck", duck_gain=0.3, premium=premium)
    assert _settle(p) == pytest.approx(0.3, abs=0.02)


@pytest.mark.parametrize("premium", [False, True])
def test_slider_level_is_honoured(premium):
    """Different duck_gain values must land at different levels -- the
    property the user checked by ear and found missing."""
    seen = [_settle(_pipe(duck_gain=g, premium=premium)) for g in (0.1, 0.5, 0.9)]
    assert seen == sorted(seen), f"premium={premium}: not monotonic -> {seen}"
    assert seen[-1] - seen[0] > 0.5, f"premium={premium}: barely moves -> {seen}"


@pytest.mark.parametrize("premium", [False, True])
def test_mix_mode_leaves_the_original_untouched(premium):
    p = _pipe(original_mode="mix", premium=premium)
    assert _settle(p) == pytest.approx(1.0)
    assert p.player.mid_gain == pytest.approx(1.0)


@pytest.mark.parametrize("premium", [False, True])
def test_mute_during_speech_drops_to_silence_then_recovers(premium):
    p = _pipe(original_mode="mute_during_speech", premium=premium)
    assert _settle(p, speaking=True) == pytest.approx(0.0, abs=0.02)
    assert _settle(p, speaking=False) == pytest.approx(1.0, abs=0.02)


@pytest.mark.parametrize("premium", [False, True])
def test_gain_returns_to_unity_when_speech_stops(premium):
    p = _pipe(original_mode="duck", duck_gain=0.2, premium=premium)
    _settle(p, speaking=True)
    assert _settle(p, speaking=False) == pytest.approx(1.0, abs=0.02)


@pytest.mark.parametrize("premium", [False, True])
def test_transition_is_ramped_not_stepped(premium):
    """The ramp is what keeps the gain change from clicking."""
    p = _pipe(original_mode="duck", duck_gain=0.0, premium=premium)
    first = p._apply_original_gain(True)
    assert 0.0 < first < 1.0, f"jumped straight to {first} (click)"


def test_premium_never_touches_the_mixer_ambient():
    """On the premium path the returned level is handed to ADRess directly
    (execute_vocal_split(level=)), never to the mixer -- mid_gain must stay at
    1.0 regardless of duck_gain, or the sides (music/SFX) would get ducked a
    second time on top of whatever the caller feeds ADRess."""
    p = _pipe(original_mode="duck", duck_gain=0.0, premium=True)
    level = _settle(p, speaking=True)
    assert level == pytest.approx(0.0, abs=0.02), "level must still reach the caller"
    assert p.player.mid_gain == pytest.approx(1.0), (
        "premium must not also duck the mixer — that would duck the music too")


def test_oss_path_keeps_centre_only_suppression():
    """Without premium, broadband mid subtraction is the ONLY dialogue
    suppression there is, so the level stays on mid_gain and the stereo music in
    the sides survives — unchanged behaviour."""
    p = _pipe(original_mode="duck", duck_gain=0.3, premium=False)
    _settle(p, speaking=True)
    assert p.player.mid_gain == pytest.approx(0.3, abs=0.02)


def test_oss_measured_output_level_actually_follows_the_slider():
    """End-to-end through the real mixer, not just the control value: on the
    OSS (no-ADRess) path, a pure-centre voice must come out ~10 dB quieter at
    30 % mid_gain."""
    import numpy as np

    from app.audio_io import _mix_to_stereo

    n = 4800
    t = np.arange(n) / 48000.0
    voice = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    amb = np.stack([voice, voice], axis=1)  # pure centre, hard-panned nowhere
    silence = np.zeros(n, dtype=np.float32)

    def level_db(mid_gain):
        out = _mix_to_stereo(silence, amb, 1.0, 1.25, True, mid_gain)
        return 20 * np.log10(max(float(np.sqrt(np.mean(out ** 2))), 1e-9))

    full, ducked = level_db(1.0), level_db(0.3)
    assert full - ducked == pytest.approx(10.5, abs=0.5), (
        f"slider moved output by only {full - ducked:.1f} dB")


# The real-module (ADRessCenterRemover) version of this property lives in
# tests/test_premium_adress.py, which is gitignored -- it imports `premium`
# directly, and scripts/check_release_hygiene.py forbids that outside
# app/pipeline.py (premium/ doesn't exist in an OSS clone at all).


def test_execute_vocal_split_forwards_level(monkeypatch):
    """Pins the plumbing from the pipeline into premium.execute_vocal_split:
    the on_chunk closure must pass the computed level through, not just
    `speaking`, or the premium path silently ignores the slider again."""
    import inspect

    src = inspect.getsource(IncomingPipeline._acquire_capture)
    body = src[src.index("def on_chunk"):]
    assert "execute_vocal_split(chunk, speaking, level)" in body, (
        "on_chunk must forward the computed level into execute_vocal_split")


def test_live_setter_updates_a_running_pipeline():
    """set_duck_gain / set_audio_mode must retarget the live pipeline, not just
    the config -- the slider is expected to act mid-session."""
    mc = ModeController.__new__(ModeController)
    p = _pipe(original_mode="duck", duck_gain=0.3)
    mc.cfg = {}
    mc._pipelines = [p]

    mc.set_duck_gain(0.75)
    mc.set_audio_mode("mute_during_speech")

    assert p._duck_gain == 0.75 and mc.cfg["duck_gain"] == 0.75
    assert p._original_mode == "mute_during_speech"
    assert mc.cfg["original_audio"] == "mute_during_speech"
    assert _settle(p, speaking=True) == pytest.approx(0.0, abs=0.02)
