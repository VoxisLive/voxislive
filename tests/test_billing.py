"""ModeController._consume_minutes — the atomic billing watermark. Money math:
the same interval must never be consumable twice, and outage time must be
skipped (not deferred)."""
import time

from app.pipeline import ModeController


def _mc():
    cfg = {"capture_backend": "driverless", "devices": {}}
    return ModeController(cfg, None, lambda *a: None, lambda *a: None)


def test_no_session_yields_nothing():
    mc = _mc()
    assert mc._consume_minutes(accrue=True) == (None, 0.0, None)


def test_accrues_elapsed_and_advances_watermark():
    mc = _mc()
    mc._session_id = "s1"
    mc._session_mode = "video"
    mc._last_report = time.monotonic() - 12.0  # 12 s ago
    sid, delta, source = mc._consume_minutes(accrue=True)
    assert sid == "s1" and source == "video"
    assert 0.19 <= delta <= 0.25  # ~0.2 min
    # Watermark advanced: an immediate second consume sees ~nothing.
    _, delta2, _ = mc._consume_minutes(accrue=True)
    assert delta2 < 0.01


def test_outage_time_is_dropped_not_deferred():
    mc = _mc()
    mc._session_id = "s1"
    mc._session_mode = "video"
    mc._last_report = time.monotonic() - 30.0
    sid, delta, _ = mc._consume_minutes(accrue=False)
    assert sid == "s1" and delta == 0.0
    # The skipped interval must NOT come back on the next accruing consume.
    _, delta2, _ = mc._consume_minutes(accrue=True)
    assert delta2 < 0.01


def test_meeting_mode_reports_incoming_source():
    mc = _mc()
    mc._session_id = "s1"
    mc._session_mode = "meeting"
    mc._last_report = time.monotonic()
    _, _, source = mc._consume_minutes(accrue=True)
    assert source == "meeting_incoming"


def test_negative_clock_glitch_clamped_to_zero():
    mc = _mc()
    mc._session_id = "s1"
    mc._session_mode = "video"
    mc._last_report = time.monotonic() + 60.0  # future watermark (clock glitch)
    _, delta, _ = mc._consume_minutes(accrue=True)
    assert delta == 0.0


# --- idle pause: an empty room must not accrue -------------------------------

class _IdleSource:
    def __init__(self, idle):
        self.idle_seconds = idle


class _IdlePipe:
    def __init__(self, idle):
        self._source = _IdleSource(idle)


def _idle_controller(*idles):
    from app.pipeline import ModeController
    mc = object.__new__(ModeController)
    mc._pipelines = [_IdlePipe(i) for i in idles]
    return mc


def test_quiet_room_stops_the_meter():
    mc = _idle_controller(300.0)
    assert mc._idle_too_long() is True


def test_recent_speech_keeps_the_meter_running():
    mc = _idle_controller(2.0)
    assert mc._idle_too_long() is False


def test_a_natural_pause_is_not_idle():
    """Well above any conversational pause — only an empty room trips it."""
    from app.pipeline import ModeController
    mc = _idle_controller(ModeController.IDLE_PAUSE_SECONDS - 1.0)
    assert mc._idle_too_long() is False


def test_meeting_is_idle_only_when_both_sides_are_quiet():
    """Two capture sources: one side still talking means the session is live."""
    mc = _idle_controller(300.0, 1.0)
    assert mc._idle_too_long() is False
    mc = _idle_controller(300.0, 300.0)
    assert mc._idle_too_long() is True


def test_unreadable_source_never_counts_as_idle():
    """Fail OPEN: if liveness cannot be established, keep billing rather than
    silently giving the session away."""
    from app.pipeline import ModeController
    mc = object.__new__(ModeController)
    mc._pipelines = [object()]
    assert mc._idle_too_long() is False


def test_idle_notice_fires_once_per_transition():
    from app.pipeline import ModeController
    mc = object.__new__(ModeController)
    seen = []
    mc.on_status = seen.append
    mc._idle_notified = False
    mc._update_idle_notice(True)
    mc._update_idle_notice(True)      # still idle — no repeat
    mc._update_idle_notice(False)
    assert len(seen) == 2
