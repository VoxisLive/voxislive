"""ModeController.skip_current_playback ('skip this sentence' control).

Mirrors the existing clear pattern shared by _swap_to_gemini and
play_free_preview: the stager's pending audio must be dropped BEFORE the
player's ring (WSOLA state before the byte-carry ring), and only the incoming
leg is ever touched — Meeting's outgoing leg has no stager and skipping it
would drop the other party mid-sentence.
"""
from app.pipeline import IncomingPipeline, ModeController
from app.webui import Bridge


class _FakeStager:
    def __init__(self, calls):
        self._calls = calls

    def clear(self):
        self._calls.append("stager.clear")


class _FakePlayer:
    def __init__(self, calls):
        self._calls = calls

    def clear_tts(self):
        self._calls.append("player.clear_tts")


def _controller_with_incoming(stager=None, player=None):
    ctl = ModeController.__new__(ModeController)
    pipe = IncomingPipeline.__new__(IncomingPipeline)
    if stager is not None:
        pipe._stager = stager
    pipe.player = player
    ctl._pipelines = [pipe]
    return ctl


def test_skip_clears_stager_then_player_in_order():
    calls = []
    ctl = _controller_with_incoming(_FakeStager(calls), _FakePlayer(calls))
    assert ctl.skip_current_playback() is True
    assert calls == ["stager.clear", "player.clear_tts"]


def test_skip_clears_player_when_engine_has_no_stager():
    # Cascade (free-tier) engine paces its own local synthesis and never
    # builds a stager — skip must still drop whatever the player is holding.
    calls = []
    ctl = _controller_with_incoming(stager=None, player=_FakePlayer(calls))
    assert ctl.skip_current_playback() is True
    assert calls == ["player.clear_tts"]


def test_skip_is_a_noop_when_idle():
    ctl = ModeController.__new__(ModeController)
    ctl._pipelines = []
    assert ctl.skip_current_playback() is False


def test_skip_survives_a_raising_stager_and_still_clears_the_player():
    calls = []

    class _BoomStager:
        def clear(self):
            raise RuntimeError("boom")

    ctl = _controller_with_incoming(_BoomStager(), _FakePlayer(calls))
    assert ctl.skip_current_playback() is True
    assert calls == ["player.clear_tts"]


def test_bridge_skip_playback_delegates_to_controller():
    b = object.__new__(Bridge)
    calls = []
    b.controller = type(
        "C", (), {"skip_current_playback": lambda self: calls.append("skip") or True})()
    assert b.skip_playback() is True
    assert calls == ["skip"]
