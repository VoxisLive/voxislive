"""Give the volume keys back to the user in vbcable mode.

The bug this fixes: in vbcable mode Voxis makes CABLE Input the Windows default
render endpoint (pipeline._switch_defaults) so other apps play into the cable.
From that moment the volume keys, the OSD slider and the mute key all act on the
CABLE — not on the headphones. Meanwhile Voxis plays the mix (translation +
ambient) straight to the headphones through its own stream, and WASAPI loopback
captures the cable's mix BEFORE the endpoint volume is applied. Net effect: the
user turns the volume down and *nothing changes* — they have lost control of
their own audio. (Driverless mode is unaffected: the default endpoint IS the
device we play to, so Windows already attenuates us.)

The fix is to mirror rather than fight: read the default endpoint's master level
(the very thing the user is moving) and apply it to our output gain. The keys
then "just work", and mute means mute.

Level is read in dB, not as the 0..1 slider position, because that is what
Windows actually applies — half-way on the slider is roughly -16 dB, not -6 —
so mirroring the scalar would feel wrong at every position but the ends.

A second, related gap: the mirror alone assumes the physical device Voxis
plays to is sitting at 0 dB. If it isn't — the common case, most people don't
run their headphones at a flat 100% — that device's OWN endpoint level
(unrelated to "default" status; Windows applies it to any stream sent there)
silently caps the output under whatever the mirror computes: the OSD shows the
cable already at 100% (nothing left to raise) while what the user actually
hears is quieter, with no way back to the device's own level because the keys
no longer reach it. `OutputLevelNeutralizer` closes that by raising the
physical device to 0 dB for the session and restoring it on stop.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading

from .paths import user_path

log = logging.getLogger("voxis")

POLL_SECONDS = 0.15   # ~7 Hz: instant to a human, invisible to the CPU
# The endpoint the keys control is whichever is DEFAULT *right now*, and that
# changes under us: the session flips the default to the cable, and the user can
# switch device mid-session. Caching the endpoint once was the original bug —
# the mirror latched onto the headphones and then watched the wrong device
# forever. Re-resolving is a COM enumeration, so do it on a slow beat, not every
# poll.
RERESOLVE_SECONDS = 1.0

# Sidecar snapshot of the physical output device's pre-neutralize level, kept
# only while OutputLevelNeutralizer is active. A crash mid-session would
# otherwise leave the device stuck raised (and, unlike a stuck DUCK, stuck
# raised means the next unrelated sound on that device plays at full volume)
# — restore_pending() (called at next launch, same hook as session_duck's)
# puts it back and only then deletes the snapshot.
_RESTORE_PATH = user_path("output_level_restore.json")


def _default_endpoint():
    """(name, IAudioEndpointVolume) for the CURRENT default render endpoint — the
    one the user's volume keys are moving, which in vbcable mode is the cable.

    pycaw's AudioDevice already hands back an activated IAudioEndpointVolume; the
    hand-rolled Activate() call the internet is full of only works on older pycaw
    (GetSpeakers used to return a raw IMMDevice)."""
    from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

    dev = AudioUtilities.GetSpeakers()
    return (getattr(dev, "FriendlyName", "?") or "?"), dev.EndpointVolume


def _endpoint_volume():
    return _default_endpoint()[1]


def _gain_from(vol) -> float:
    if vol.GetMute():
        return 0.0
    db = float(vol.GetMasterVolumeLevel())      # dB, e.g. -16.0
    return max(0.0, min(1.0, math.pow(10.0, db / 20.0)))


def _find_render_endpoint(name_substr: str, devices=None):
    """The IAudioEndpointVolume for the render endpoint whose friendly name
    contains `name_substr` (case-insensitive), or None if not present.

    `devices` is injectable for tests; production always re-enumerates (no
    caching) since this only runs once per session start/stop."""
    needle = (name_substr or "").strip().lower()
    if not needle:
        return None
    if devices is None:
        from pycaw.pycaw import AudioUtilities, EDataFlow  # noqa: PLC0415
        try:
            devices = AudioUtilities.GetAllDevices(data_flow=EDataFlow.eRender.value)
        except Exception:  # noqa: BLE001
            return None
    for d in devices:
        try:
            fn = getattr(d, "FriendlyName", None) or ""
            if needle in fn.lower():
                return d.EndpointVolume
        except Exception:  # noqa: BLE001
            continue
    return None


def _write_snapshot(device_name: str, db: float, mute: bool) -> None:
    tmp = _RESTORE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"device": device_name, "db": db, "mute": mute}, f)
        os.replace(tmp, _RESTORE_PATH)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _clear_snapshot() -> None:
    try:
        if os.path.exists(_RESTORE_PATH):
            os.remove(_RESTORE_PATH)
    except OSError:
        pass


def restore_pending() -> None:
    """Undo a neutralize left behind by a crash/kill of a previous run.

    Only restores if the device still looks like the neutralize left it (at or
    near 0 dB) — if the user already set their own level since the crash, that
    is respected and left alone, mirroring session_duck's raise-only rule in
    the opposite direction. The snapshot is removed after one pass either way;
    a transient COM failure just leaves it for the next launch."""
    try:
        if not os.path.exists(_RESTORE_PATH):
            return
        with open(_RESTORE_PATH, "r", encoding="utf-8") as f:
            entry = json.load(f) or {}
    except (OSError, ValueError):
        _clear_snapshot()
        return
    device_name = entry.get("device") or ""
    try:
        orig_db = float(entry.get("db"))
    except (TypeError, ValueError):
        _clear_snapshot()
        return
    orig_mute = bool(entry.get("mute"))
    if not device_name:
        _clear_snapshot()
        return
    try:
        import comtypes  # noqa: PLC0415
        comtypes.CoInitialize()
    except Exception:  # noqa: BLE001
        pass
    try:
        vol = _find_render_endpoint(device_name)
        if vol is not None:
            try:
                if float(vol.GetMasterVolumeLevel()) >= -0.5:
                    vol.SetMasterVolumeLevel(orig_db, None)
                    vol.SetMute(orig_mute, None)
            except Exception:  # noqa: BLE001
                pass
    finally:
        _clear_snapshot()
        try:
            import comtypes  # noqa: PLC0415
            comtypes.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


class OutputLevelNeutralizer:
    """Raises the PHYSICAL playback device to 0 dB / unmuted for a vbcable
    session and restores its original level on stop. See the module docstring
    for the bug this closes. Best-effort and self-restoring: any COM failure
    leaves the device alone.
    """

    def __init__(self, device_name: str):
        self._device_name = device_name
        self._vol = None
        self._orig_db = None
        self._orig_mute = None

    def apply(self):
        try:
            vol = _find_render_endpoint(self._device_name)
            if vol is None:
                return
            orig_db = float(vol.GetMasterVolumeLevel())
            orig_mute = bool(vol.GetMute())
            if orig_db < -0.5 or orig_mute:
                vol.SetMasterVolumeLevel(0.0, None)
                vol.SetMute(False, None)
                # Only worth a crash-recovery snapshot when we actually changed
                # something — nothing to restore otherwise.
                _write_snapshot(self._device_name, orig_db, orig_mute)
            self._vol, self._orig_db, self._orig_mute = vol, orig_db, orig_mute
        except Exception:  # noqa: BLE001
            log.info("output neutralizer: could not raise '%s'",
                      self._device_name, exc_info=True)

    def restore(self):
        if self._vol is None:
            return
        try:
            self._vol.SetMasterVolumeLevel(self._orig_db, None)
            self._vol.SetMute(self._orig_mute, None)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._vol, self._orig_db, self._orig_mute = None, None, None
            _clear_snapshot()


class EndpointVolumeMirror:
    """Follows the default endpoint's level onto `player.master_gain` until
    stopped. Best-effort by contract: if COM or pycaw fails we leave the gain at
    1.0 — losing the mirror is a nuisance, muting the session would be a fault."""

    def __init__(self, player):
        self._player = player
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="endpoint-volume")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        # The gain lives on the player; hand it back at full scale so a later
        # session (or the free-voice preview's own Player) never starts muted.
        try:
            self._player.master_gain = 1.0
        except Exception:  # noqa: BLE001
            pass

    def _run(self):
        import time  # noqa: PLC0415

        import comtypes  # noqa: PLC0415

        try:
            comtypes.CoInitialize()
        except Exception:  # noqa: BLE001
            pass
        vol, resolved_at, watching = None, 0.0, None
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if vol is None or (now - resolved_at) >= RERESOLVE_SECONDS:
                    try:
                        name, vol = _default_endpoint()
                        resolved_at = now
                        if name != watching:
                            # Names the device the keys actually control. If this
                            # ever says the headphones during a vbcable session,
                            # the mirror started before the default was flipped.
                            log.info("volume mirror: following '%s'", name)
                            watching = name
                    except Exception as exc:  # noqa: BLE001
                        if vol is None:
                            log.info("endpoint volume mirror unavailable (%s) — "
                                     "volume keys will not reach the translation", exc)
                            return
                try:
                    self._player.master_gain = _gain_from(vol)
                except Exception:  # noqa: BLE001 - a transient COM fault must not
                    vol = None     # kill the mirror; re-resolve and carry on
                self._stop.wait(POLL_SECONDS)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass
