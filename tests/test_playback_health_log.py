"""Playback-health telemetry: delta-only logging, and Qwen's duplicate-audio
counter finally has a consumer.

The log high-water mark used to live in a ModeController dict keyed by
id(stager). A stager that was collected and replaced could land on the same
address and inherit the dead one's mark, silently suppressing the next real
compression/trim event. It now lives on the stager, so a replacement starts
clean by construction.
"""
import logging

from app.pipeline import ModeController
from app.playback_sync import AdaptivePlaybackStager


class _FakeStager:
    """Only the fields _log_playback_health reads."""

    def __init__(self, backlog=0.0, skipped=0.0, sped=0.0, speed=1.0):
        self.backlog_s = backlog
        self.skipped_s = skipped
        self.sped_s = sped
        self.speed = speed
        self.logged_watermark = (0.0, 0.0)
        self.logged_dup_audio = 0


class _FakePipe:
    def __init__(self, stager, engine="qwen", dup=0):
        self._stager = stager
        self._engine = engine
        self.translator = type("T", (), {"_dup_audio_count": dup})()


def _controller(*pipes):
    mc = ModeController.__new__(ModeController)
    mc._pipelines = list(pipes)
    return mc


def _lines(caplog):
    return [r.message for r in caplog.records if "playback health" in r.message]


def test_quiet_playback_logs_nothing(caplog):
    mc = _controller(_FakePipe(_FakeStager()))
    with caplog.at_level(logging.INFO, logger="voxis"):
        mc._log_playback_health()
    assert _lines(caplog) == []


def test_compression_logs_once_then_stays_quiet(caplog):
    stager = _FakeStager(sped=1.5, speed=1.15)
    mc = _controller(_FakePipe(stager))
    with caplog.at_level(logging.INFO, logger="voxis"):
        mc._log_playback_health()
        assert len(_lines(caplog)) == 1
        mc._log_playback_health()          # nothing new happened
        assert len(_lines(caplog)) == 1
        stager.sped_s = 2.4                # more compression -> log again
        mc._log_playback_health()
        assert len(_lines(caplog)) == 2


def test_duplicate_audio_is_surfaced(caplog):
    """Qwen's _dup_audio_count was read by nothing but a unit test, even though
    duplicated/overlapping server audio is a direct cause of choppy playback."""
    stager = _FakeStager()
    mc = _controller(_FakePipe(stager, dup=7))
    with caplog.at_level(logging.INFO, logger="voxis"):
        mc._log_playback_health()
    lines = _lines(caplog)
    assert len(lines) == 1 and "dup_audio=7" in lines[0]
    assert stager.logged_dup_audio == 7


def test_engines_without_the_counter_report_zero(caplog):
    """Gemini and cascade translators have no _dup_audio_count attribute."""
    stager = _FakeStager(backlog=3.0)
    pipe = _FakePipe(stager, engine="gemini")
    pipe.translator = object()
    mc = _controller(pipe)
    with caplog.at_level(logging.INFO, logger="voxis"):
        mc._log_playback_health()
    assert "dup_audio=0" in _lines(caplog)[0]


def test_a_replacement_stager_starts_with_a_clean_watermark(caplog):
    """The id()-keyed dict could hand a fresh stager a dead one's high-water
    mark. Holding it on the instance makes that impossible."""
    first = _FakeStager(sped=9.0)
    pipe = _FakePipe(first)
    mc = _controller(pipe)
    with caplog.at_level(logging.INFO, logger="voxis"):
        mc._log_playback_health()
        assert len(_lines(caplog)) == 1
        # Engine swap: a brand-new stager whose counters restart at 0.
        pipe._stager = _FakeStager(sped=0.5)
        mc._log_playback_health()
    assert len(_lines(caplog)) == 2, "a fresh stager's first event was swallowed"


def test_pipeline_without_a_stager_is_skipped(caplog):
    """A cascade-routed pipeline (paces its own local synthesis) never builds
    a stager at all, on either leg — this must not raise or fabricate a log."""
    pipe = _FakePipe(None)
    with caplog.at_level(logging.INFO, logger="voxis"):
        _controller(pipe)._log_playback_health()
    assert _lines(caplog) == []


def test_real_stager_exposes_a_clean_watermark(caplog):
    """Pins the contract against the real class, not just the fake above: a
    freshly built stager must satisfy _log_playback_health unmodified."""
    class _Ring:
        fill = 0

    class _Player:
        rate = 24000
        tts = _Ring()

    stager = AdaptivePlaybackStager(_Player(), input_rate=24000)
    try:
        assert stager.logged_watermark == (0.0, 0.0)
        assert stager.logged_dup_audio == 0
        pipe = _FakePipe(stager, engine="qwen", dup=3)
        with caplog.at_level(logging.INFO, logger="voxis"):
            _controller(pipe)._log_playback_health()
        assert "dup_audio=3" in _lines(caplog)[0]
        assert stager.logged_dup_audio == 3
    finally:
        stager.stop()
