"""Background app.json manifest check (webui._check_app_manifest /
_parse_semver): the update-available badge must only fire on a genuinely
newer version, and a bad/missing manifest must never raise or spam an event.
"""
import queue
import threading

from app import voxis_client as vc
from app import webui
from app.webui import Bridge, _parse_semver


def test_parse_semver_orders_correctly():
    assert _parse_semver("1.0.54") < _parse_semver("1.0.55")
    assert _parse_semver("1.0.54") == _parse_semver("1.0.54")
    assert _parse_semver("1.1.0") > _parse_semver("1.0.99")


def test_parse_semver_rejects_garbage():
    assert _parse_semver("garbage") is None
    assert _parse_semver("") is None
    assert _parse_semver(None) is None


class _SyncThread:
    """Runs the manifest-check worker inline so the test is deterministic."""

    def __init__(self, target=None, daemon=None, name=None):
        self._target = target

    def start(self):
        self._target()


def _bare_bridge():
    b = object.__new__(Bridge)
    b._manifest_check_started = False
    b._events = queue.Queue(maxsize=10)
    b._push_q = queue.Queue(maxsize=10)
    b._event_seq = 0
    b._seq_lock = threading.Lock()
    b._main_window = None
    return b


def _events_of(b):
    """_put_event queues {"seq": n, "ev": [type, payload]} dicts (see
    Bridge._put_event) — unwrap to the (type, payload) tuples tests want."""
    out = []
    while not b._events.empty():
        out.append(tuple(b._events.get_nowait()["ev"]))
    return out


def test_newer_remote_version_fires_update_available(monkeypatch):
    monkeypatch.setattr(webui, "APP_VERSION", "1.0.54")
    monkeypatch.setattr(webui.threading, "Thread", _SyncThread)
    monkeypatch.setattr(vc, "fetch_app_manifest",
                         lambda: {"app": {"version": "1.0.55"}})
    b = _bare_bridge()
    b._maybe_check_app_manifest()
    assert ("update_available", {"version": "1.0.55"}) in _events_of(b)


def test_same_or_older_remote_version_is_silent(monkeypatch):
    monkeypatch.setattr(webui, "APP_VERSION", "1.0.54")
    monkeypatch.setattr(webui.threading, "Thread", _SyncThread)
    monkeypatch.setattr(vc, "fetch_app_manifest",
                         lambda: {"app": {"version": "1.0.54"}})
    b = _bare_bridge()
    b._maybe_check_app_manifest()
    assert _events_of(b) == []


def test_missing_manifest_is_silent(monkeypatch):
    monkeypatch.setattr(webui, "APP_VERSION", "1.0.54")
    monkeypatch.setattr(webui.threading, "Thread", _SyncThread)
    monkeypatch.setattr(vc, "fetch_app_manifest", lambda: None)
    b = _bare_bridge()
    b._maybe_check_app_manifest()
    assert _events_of(b) == []


def test_malformed_version_field_is_silent(monkeypatch):
    monkeypatch.setattr(webui, "APP_VERSION", "1.0.54")
    monkeypatch.setattr(webui.threading, "Thread", _SyncThread)
    monkeypatch.setattr(vc, "fetch_app_manifest",
                         lambda: {"app": {"version": "not-a-version"}})
    b = _bare_bridge()
    b._maybe_check_app_manifest()
    assert _events_of(b) == []


def test_check_runs_at_most_once_per_launch(monkeypatch):
    monkeypatch.setattr(webui, "APP_VERSION", "1.0.54")
    monkeypatch.setattr(webui.threading, "Thread", _SyncThread)
    calls = []

    def fake_fetch():
        calls.append(1)
        return {"app": {"version": "1.0.55"}}

    monkeypatch.setattr(vc, "fetch_app_manifest", fake_fetch)
    b = _bare_bridge()
    b._maybe_check_app_manifest()
    b._maybe_check_app_manifest()
    assert len(calls) == 1
