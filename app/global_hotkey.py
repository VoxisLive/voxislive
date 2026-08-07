"""Narrow, ctypes-only Win32 global hotkey registration (RegisterHotKey).

Replaces `keyboard.add_hotkey` for the always-on bound-hotkey path in
webui.py's `_register_hotkeys`. `keyboard.add_hotkey` installs a process-wide
WH_KEYBOARD_LL hook for the entire app lifetime -- a pattern AV/EDR
heuristics associate with keyloggers, and exactly why requirements.txt flags
the package as admin/AV-sensitive. RegisterHotKey needs no hook: it asks the
OS to own a small, fixed set of known combos and delivers WM_HOTKEY on a
plain per-thread message loop -- the same mechanism most Windows utilities
use for global shortcuts. Hotkeys registered this way are also released
automatically by the OS when the owning thread exits, so a hard process kill
leaves nothing to clean up.

Deliberately narrow scope: this only recognizes the modifier+single-key
combos the Settings hotkey recorder can actually produce (webui.py's
`capture_hotkey`, still `keyboard`-based). Detecting an arbitrary combo the
user is CURRENTLY pressing -- as opposed to firing on one already known --
is a different problem RegisterHotKey can't solve, so that capture flow
stays on `keyboard`; it now runs only for the few seconds a user has the
hotkey-recording box open in Settings, not for the app's whole lifetime.
An unparseable or already-taken combo is skipped and logged, never raised --
matches the fail-soft contract `_register_hotkeys` already had.
"""
import ctypes
import logging
import threading
from ctypes import wintypes

_log = logging.getLogger("voxis.global_hotkey")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # one WM_HOTKEY per press, not one per OS key-repeat tick

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# Combo strings are produced/parsed by the `keyboard` package's own naming
# (webui.py's capture_hotkey records via keyboard.read_hotkey, and
# config.DEFAULTS["hotkeys"] hand-writes the same style) -- see
# keyboard._canonical_names for the full vocabulary this mirrors a subset of.
_MODIFIER_BITS = {
    "alt": MOD_ALT, "left alt": MOD_ALT, "right alt": MOD_ALT,
    "ctrl": MOD_CONTROL, "left ctrl": MOD_CONTROL, "right ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT, "left shift": MOD_SHIFT, "right shift": MOD_SHIFT,
    "windows": MOD_WIN, "left windows": MOD_WIN, "right windows": MOD_WIN,
    "alt gr": MOD_CONTROL | MOD_ALT,  # AltGr is physically Ctrl+Alt on Windows
}


def _build_vk_table():
    vk = {chr(ord("a") + i): 0x41 + i for i in range(26)}
    vk.update({str(i): 0x30 + i for i in range(10)})
    vk.update({f"f{i}": 0x70 + (i - 1) for i in range(1, 25)})  # VK_F1..VK_F24
    vk.update({
        "space": 0x20,
        "enter": 0x0D, "return": 0x0D,
        "esc": 0x1B, "escape": 0x1B,
        "tab": 0x09,
        "backspace": 0x08,
        "delete": 0x2E, "del": 0x2E,
        "insert": 0x2D, "ins": 0x2D,
        "home": 0x24,
        "end": 0x23,
        "page up": 0x21, "pageup": 0x21, "pgup": 0x21,
        "page down": 0x22, "pagedown": 0x22, "pgdown": 0x22,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "print screen": 0x2C, "prtscn": 0x2C,
        "scroll lock": 0x91,
        "pause": 0x13,
        "caps lock": 0x14,
        "num lock": 0x90,
        "menu": 0x5D, "apps": 0x5D,
    })
    return vk


_VK = _build_vk_table()


def _parse_combo(combo):
    """'ctrl+alt+v' -> (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_V).

    None on anything this narrow parser doesn't recognize: an unknown token,
    no base key, or more than one base key. Never raises."""
    if not combo or not isinstance(combo, str):
        return None
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    mods = MOD_NOREPEAT
    vk = None
    for part in parts:
        if part in _MODIFIER_BITS:
            mods |= _MODIFIER_BITS[part]
        elif vk is None and part in _VK:
            vk = _VK[part]
        else:
            return None
    if vk is None:
        return None
    return mods, vk


class GlobalHotkeys:
    """Owns one dedicated message-pump thread (RegisterHotKey posts WM_HOTKEY
    to the registering thread's queue, so registration and the pump must
    live on the same thread). `set_bindings` fully replaces whatever was
    previously registered; `stop` tears the thread down."""

    def __init__(self):
        self._thread = None
        self._thread_id = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def set_bindings(self, bindings):
        """bindings: dict[action_id -> (combo_str, callback)]. Blocks until
        registration finishes (or 2s pass) so a caller inspecting state right
        after this returns sees the final result, matching the old
        synchronous `keyboard.add_hotkey` calls this replaces."""
        with self._lock:
            self._stop_locked()
            if not bindings:
                return
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run, args=(dict(bindings),),
                daemon=True, name="voxis-global-hotkeys")
            self._thread.start()
            self._ready.wait(2.0)

    def stop(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        thread, tid = self._thread, self._thread_id
        self._thread = None
        self._thread_id = None
        if tid is not None:
            user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        if thread is not None:
            thread.join(timeout=2.0)

    def _run(self, bindings):
        self._thread_id = kernel32.GetCurrentThreadId()
        registered = {}
        next_id = 1
        for action, (combo, callback) in bindings.items():
            parsed = _parse_combo(combo)
            if not parsed:
                _log.warning("unparseable hotkey combo %r for %r", combo, action)
                next_id += 1
                continue
            mods, vk = parsed
            if user32.RegisterHotKey(None, next_id, mods, vk):
                registered[next_id] = callback
            else:
                _log.warning(
                    "RegisterHotKey failed for %r (%r) -- likely already "
                    "bound by another app", action, combo)
            next_id += 1
        self._ready.set()
        try:
            msg = wintypes.MSG()
            msg_ptr = ctypes.pointer(msg)
            while True:
                ret = user32.GetMessageW(msg_ptr, None, 0, 0)
                if ret <= 0:  # WM_QUIT, or an error -- either way, stop pumping
                    break
                if msg.message == WM_HOTKEY:
                    cb = registered.get(msg.wParam)
                    if cb:
                        try:
                            cb()
                        except Exception:
                            _log.exception("hotkey callback raised")
        finally:
            for hotkey_id in registered:
                try:
                    user32.UnregisterHotKey(None, hotkey_id)
                except Exception:
                    pass


_pump = GlobalHotkeys()


def set_bindings(bindings):
    _pump.set_bindings(bindings)


def stop():
    _pump.stop()
