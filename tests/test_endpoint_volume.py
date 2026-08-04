"""The volume keys must reach what the user hears.

In vbcable mode Windows' default endpoint is the cable, so the keys stop
controlling the headphones Voxis plays to. The mirror copies that endpoint's
level onto our output. Two things must hold: the mapping matches what Windows
actually applies (dB, not slider position), and a failure can never leave the
session silent.

A second class of test covers OutputLevelNeutralizer: the physical device
Voxis plays to keeps its OWN endpoint level regardless of "default" status, so
if it was sitting below 0 dB the mirror alone still caps the output under
whatever it computes, with no way back to it via the keys. Neutralizing that
device (and restoring it on stop, crash-safely) closes the gap.
"""
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import endpoint_volume as ev  # noqa: E402


class _Vol:
    def __init__(self, db=0.0, mute=False):
        self._db, self._mute = db, mute

    def GetMute(self):          # noqa: N802 - COM interface name
        return self._mute

    def SetMute(self, m, ctx):  # noqa: N802
        self._mute = m

    def GetMasterVolumeLevel(self):  # noqa: N802
        return self._db

    def SetMasterVolumeLevel(self, db, ctx):  # noqa: N802
        self._db = db


class _Dev:
    def __init__(self, name, vol):
        self.FriendlyName = name
        self.EndpointVolume = vol


def test_full_scale_is_unity():
    assert ev._gain_from(_Vol(db=0.0)) == pytest.approx(1.0)


def test_mute_means_silence():
    assert ev._gain_from(_Vol(db=-6.0, mute=True)) == 0.0


def test_level_follows_decibels_not_the_slider():
    # Windows' slider at ~34% sits near -16 dB → ~0.16 amplitude. Mirroring the
    # slider position (0.34) would be more than twice as loud as Windows itself.
    assert ev._gain_from(_Vol(db=-16.0)) == pytest.approx(0.158, abs=0.005)
    assert ev._gain_from(_Vol(db=-6.02)) == pytest.approx(0.5, abs=0.01)


def test_gain_is_clamped():
    assert ev._gain_from(_Vol(db=+12.0)) == 1.0     # never amplify past unity
    assert ev._gain_from(_Vol(db=-96.0)) >= 0.0


def test_stop_hands_the_gain_back():
    # A mirror that stopped (or crashed) must not leave the next session — or the
    # free-voice preview's own Player — stuck at a stale, quiet gain.
    player = types.SimpleNamespace(master_gain=0.1)
    m = ev.EndpointVolumeMirror(player)
    m.stop()
    assert player.master_gain == 1.0


# ---------- _find_render_endpoint ----------

def test_find_render_endpoint_matches_by_substring():
    vol = _Vol(db=-10.0)
    devices = [_Dev("Speakers (Realtek)", _Vol()), _Dev("Headphones (USB Audio)", vol)]
    found = ev._find_render_endpoint("headphones", devices)
    assert found is vol


def test_find_render_endpoint_no_match_returns_none():
    devices = [_Dev("Speakers (Realtek)", _Vol())]
    assert ev._find_render_endpoint("headphones", devices) is None


def test_find_render_endpoint_blank_query_returns_none():
    assert ev._find_render_endpoint("", [_Dev("Speakers", _Vol())]) is None


# ---------- OutputLevelNeutralizer ----------

@pytest.fixture
def snap_path(tmp_path, monkeypatch):
    path = str(tmp_path / "output_level_restore.json")
    monkeypatch.setattr(ev, "_RESTORE_PATH", path)
    return path


def _patch_find(monkeypatch, vol):
    monkeypatch.setattr(ev, "_find_render_endpoint", lambda name, devices=None: vol)


def test_neutralize_raises_a_lowered_device(monkeypatch, snap_path):
    vol = _Vol(db=-12.0)
    _patch_find(monkeypatch, vol)
    n = ev.OutputLevelNeutralizer("Headphones")
    n.apply()
    assert vol.GetMasterVolumeLevel() == 0.0
    assert vol.GetMute() is False
    assert os.path.exists(snap_path)  # crash-recovery snapshot written


def test_neutralize_leaves_a_full_device_untouched_and_writes_no_snapshot(monkeypatch, snap_path):
    vol = _Vol(db=0.0)
    _patch_find(monkeypatch, vol)
    n = ev.OutputLevelNeutralizer("Headphones")
    n.apply()
    assert vol.GetMasterVolumeLevel() == 0.0
    assert not os.path.exists(snap_path)  # nothing changed, nothing to restore


def test_restore_puts_the_original_level_back(monkeypatch, snap_path):
    vol = _Vol(db=-12.0, mute=True)
    _patch_find(monkeypatch, vol)
    n = ev.OutputLevelNeutralizer("Headphones")
    n.apply()
    n.restore()
    assert vol.GetMasterVolumeLevel() == pytest.approx(-12.0)
    assert vol.GetMute() is True
    assert not os.path.exists(snap_path)  # cleared


def test_restore_without_apply_is_noop():
    n = ev.OutputLevelNeutralizer("Headphones")
    n.restore()  # must not raise


def test_missing_device_is_a_noop(monkeypatch, snap_path):
    _patch_find(monkeypatch, None)
    n = ev.OutputLevelNeutralizer("Nonexistent Device")
    n.apply()  # must not raise
    assert not os.path.exists(snap_path)


# ---------- restore_pending (crash recovery) ----------

def test_restore_pending_puts_a_stuck_raised_device_back(monkeypatch, snap_path):
    vol = _Vol(db=0.0)  # still raised, as the neutralize left it — a crash mid-session
    monkeypatch.setattr(ev, "_find_render_endpoint", lambda name, devices=None: vol)
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump({"device": "Headphones", "db": -12.0, "mute": False}, f)
    ev.restore_pending()
    assert vol.GetMasterVolumeLevel() == pytest.approx(-12.0)
    assert not os.path.exists(snap_path)


def test_restore_pending_never_fights_a_level_the_user_already_set(monkeypatch, snap_path):
    vol = _Vol(db=-30.0)  # user already turned it down themselves since the crash
    monkeypatch.setattr(ev, "_find_render_endpoint", lambda name, devices=None: vol)
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump({"device": "Headphones", "db": -12.0, "mute": False}, f)
    ev.restore_pending()
    assert vol.GetMasterVolumeLevel() == pytest.approx(-30.0)  # untouched
    assert not os.path.exists(snap_path)  # still consumed


def test_restore_pending_with_no_snapshot_is_noop(snap_path):
    ev.restore_pending()  # must not raise
    assert not os.path.exists(snap_path)


def test_restore_pending_discards_a_corrupt_snapshot(snap_path):
    with open(snap_path, "w", encoding="utf-8") as f:
        f.write("{not json")
    ev.restore_pending()
    assert not os.path.exists(snap_path)
