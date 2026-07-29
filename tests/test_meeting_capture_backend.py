"""Meeting mode must never take the vbcable capture path.

Both directions would share one virtual cable: the outgoing leg writes the
translated voice into CABLE Input and the vbcable capture reads CABLE Output,
so Voxis re-translates its own output back into the user's language (a phantom
third voice, reported from the field). Driverless capture excludes our own
process at the OS level, so the loop cannot form.
"""
import pytest

from app import pipeline


class _StubPremium:
    """Stands in for the closed premium module: a machine WITH a cable."""

    @staticmethod
    def resolve_capture_backend(cfg):
        return "vbcable"


def _mc(monkeypatch, mode_fails=True):
    monkeypatch.setattr(pipeline, "_premium", _StubPremium)
    monkeypatch.setattr(pipeline.sysaudio, "is_supported", lambda: True)
    monkeypatch.setattr(pipeline.audio_io, "refresh", lambda: None)
    monkeypatch.setattr(pipeline.voxis_client, "report_event_async",
                        lambda *a, **k: None)
    cfg = {"capture_backend": "driverless", "devices": {}}
    mc = pipeline.ModeController(cfg, None, lambda *a: None, lambda *a: None)
    mc.resolve = lambda target, **kw: ("gemini", "key", "model")
    # Stop right after the backend has been resolved: the real _build opens audio
    # devices and a Live session, neither of which exists in a test.
    if mode_fails:
        monkeypatch.setattr(mc, "_build",
                            lambda mode: (_ for _ in ()).throw(RuntimeError("no audio")))
    return mc


def _start(mc, mode):
    """Runs start() far enough to resolve the backend; the stubbed _build then
    fails the session, which is the point — no real devices are touched."""
    with pytest.raises(RuntimeError):
        mc.start(mode)


def test_meeting_forces_driverless_even_with_a_cable(monkeypatch):
    mc = _mc(monkeypatch)
    _start(mc, "meeting")
    assert mc.cfg["capture_backend"] == "driverless"


def test_video_still_auto_routes_to_the_cable(monkeypatch):
    mc = _mc(monkeypatch)
    _start(mc, "video")
    assert mc.cfg["capture_backend"] == "vbcable"


def test_meeting_overrides_a_previously_resolved_cable(monkeypatch):
    """A video session leaves vbcable in cfg; the next meeting must not inherit it."""
    mc = _mc(monkeypatch)
    _start(mc, "video")
    assert mc.cfg["capture_backend"] == "vbcable"
    _start(mc, "meeting")
    assert mc.cfg["capture_backend"] == "driverless"


def test_meeting_stays_driverless_without_premium(monkeypatch):
    """OSS build: no premium module at all, meeting must still be driverless."""
    mc = _mc(monkeypatch)
    monkeypatch.setattr(pipeline, "_premium", None)
    _start(mc, "meeting")
    assert mc.cfg["capture_backend"] == "driverless"


def test_meeting_leaves_the_default_render_endpoint_alone(monkeypatch):
    """The render flip to CABLE Input only belongs to the vbcable capture path.

    In a meeting it would push the conferencing app's own playback into the
    cable that also feeds Teams' microphone — the other party hearing itself.
    """
    mc = _mc(monkeypatch)
    mc.cfg["capture_backend"] = "driverless"
    mc._outgoing_ok = True
    switched = []

    class _Endpoints:
        @staticmethod
        def get_default(kind):
            return ("id-mic", "Headset Microphone")

        @staticmethod
        def find_endpoint_id(name):
            return f"id::{name}"

        @staticmethod
        def set_default(dev_id):
            switched.append(dev_id)

    monkeypatch.setattr(pipeline.sysaudio, "supports_endpoints", lambda: True)
    monkeypatch.setattr(pipeline.sysaudio, "endpoints", lambda: _Endpoints)
    monkeypatch.setattr("app.config.save_config", lambda cfg: None)
    mc.cfg["devices"] = {"meeting_virtual_mic": "CABLE Output (VB-Audio Virtual Cable)"}

    mc._switch_defaults("meeting")

    assert switched == ["id::CABLE Output (VB-Audio Virtual Cable)"]
    assert not any("CABLE Input" in d for d in switched)
