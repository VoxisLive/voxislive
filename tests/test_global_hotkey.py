"""app/global_hotkey.py -- the ctypes/RegisterHotKey replacement for
`keyboard.add_hotkey` on the always-on bound-hotkey path (see that module's
docstring for why). Two things are pinned: `_parse_combo`, since a silent
misparse would mean a user's saved hotkey quietly stops firing; and
`GlobalHotkeys`' register/fire/replace/stop lifecycle, exercised end to end
against a fake user32/kernel32 so the suite never touches a real global
hotkey on the machine running it.
"""
import queue
import threading

import pytest

from app import global_hotkey

# --- _parse_combo ------------------------------------------------------------

@pytest.mark.parametrize("combo,expected_vk", [
    ("ctrl+alt+1", 0x31),
    ("ctrl+alt+2", 0x32),
    ("ctrl+alt+0", 0x30),
    ("ctrl+alt+o", 0x4F),
    ("ctrl+alt+v", 0x56),
])
def test_parse_combo_matches_config_defaults(combo, expected_vk):
    # These four are literally config.DEFAULTS["hotkeys"] -- if this parser
    # can't handle them, every fresh install's default hotkeys silently stop
    # working the moment this module goes live.
    mods, vk = global_hotkey._parse_combo(combo)
    assert vk == expected_vk
    assert mods & global_hotkey.MOD_CONTROL
    assert mods & global_hotkey.MOD_ALT
    assert mods & global_hotkey.MOD_NOREPEAT


def test_parse_combo_function_key():
    mods, vk = global_hotkey._parse_combo("ctrl+shift+f9")
    assert vk == 0x78  # VK_F9
    assert mods & global_hotkey.MOD_CONTROL
    assert mods & global_hotkey.MOD_SHIFT
    assert not mods & global_hotkey.MOD_ALT


def test_parse_combo_case_and_whitespace_insensitive():
    a = global_hotkey._parse_combo("ctrl+alt+v")
    b = global_hotkey._parse_combo(" CTRL + ALT + V ")
    assert a == b


def test_parse_combo_sided_modifiers_map_to_generic_bit():
    mods, vk = global_hotkey._parse_combo("left ctrl+v")
    assert mods & global_hotkey.MOD_CONTROL
    assert vk == 0x56


def test_parse_combo_alt_gr_is_ctrl_plus_alt():
    mods, _ = global_hotkey._parse_combo("alt gr+e")
    assert mods & global_hotkey.MOD_CONTROL
    assert mods & global_hotkey.MOD_ALT


def test_parse_combo_named_key_with_space_in_its_name():
    _mods, vk = global_hotkey._parse_combo("ctrl+alt+page up")
    assert vk == 0x21


def test_parse_combo_bare_key_no_modifier_is_valid():
    # capture_hotkey()/keyboard.read_hotkey() allow a modifier-less combo
    # (e.g. a lone F9); this parser must not reject what the recorder can
    # legitimately produce.
    mods, vk = global_hotkey._parse_combo("f9")
    assert vk == 0x78
    assert mods == global_hotkey.MOD_NOREPEAT


@pytest.mark.parametrize("bad", [
    None, "", "   ", "ctrl+alt", "ctrl+alt+doesnotexist", "ctrl+v+b", 42,
])
def test_parse_combo_rejects_unparseable_input(bad):
    assert global_hotkey._parse_combo(bad) is None


# --- GlobalHotkeys lifecycle, against a fake user32/kernel32 ----------------

class _FakeUser32:
    """Enough of user32 to drive GlobalHotkeys' real _run loop: a blocking
    GetMessageW fed by PostThreadMessageW, so WM_QUIT actually unblocks it
    the same way the real message loop would."""

    def __init__(self):
        self.registered = {}       # hotkey_id -> (mods, vk)
        self.register_result = {}  # hotkey_id -> bool override, default True
        self.unregistered = []
        self._queue = queue.Queue()

    def RegisterHotKey(self, hwnd, hotkey_id, mods, vk):
        ok = self.register_result.get(hotkey_id, True)
        if ok:
            self.registered[hotkey_id] = (mods, vk)
        return 1 if ok else 0

    def UnregisterHotKey(self, hwnd, hotkey_id):
        self.unregistered.append(hotkey_id)
        return 1

    def PostThreadMessageW(self, tid, message, wparam, lparam):
        self._queue.put((message, wparam, lparam))
        return 1

    def GetMessageW(self, msg_ptr, hwnd, wmin, wmax):
        message, wparam, lparam = self._queue.get()
        msg_ptr.contents.message = message
        msg_ptr.contents.wParam = wparam
        msg_ptr.contents.lParam = lparam
        return 0 if message == global_hotkey.WM_QUIT else 1


class _FakeKernel32:
    def GetCurrentThreadId(self):
        return 4242


@pytest.fixture
def fakes(monkeypatch):
    fake_user32 = _FakeUser32()
    monkeypatch.setattr(global_hotkey, "user32", fake_user32)
    monkeypatch.setattr(global_hotkey, "kernel32", _FakeKernel32())
    return fake_user32


def test_set_bindings_registers_parsed_combo(fakes):
    pump = global_hotkey.GlobalHotkeys()
    fired = threading.Event()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", fired.set)})
        assert len(fakes.registered) == 1
        mods, vk = next(iter(fakes.registered.values()))
        assert vk == 0x31
        assert mods & global_hotkey.MOD_CONTROL and mods & global_hotkey.MOD_ALT
    finally:
        pump.stop()


def test_set_bindings_fires_bound_callback_on_matching_id(fakes):
    pump = global_hotkey.GlobalHotkeys()
    fired = threading.Event()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", fired.set)})
        hotkey_id = next(iter(fakes.registered))
        fakes.PostThreadMessageW(pump._thread_id, global_hotkey.WM_HOTKEY, hotkey_id, 0)
        assert fired.wait(2.0)
    finally:
        pump.stop()


def test_set_bindings_skips_unparseable_combo_but_registers_the_rest(fakes):
    pump = global_hotkey.GlobalHotkeys()
    try:
        pump.set_bindings({
            "video": ("ctrl+alt+1", lambda: None),
            "stop": ("not a real combo", lambda: None),
        })
        assert len(fakes.registered) == 1  # only the parseable one
    finally:
        pump.stop()


def test_set_bindings_handles_registerhotkey_failure_without_raising(fakes):
    # Simulate "combo already bound by another app": RegisterHotKey returns
    # FALSE. Must not raise, and the failed id must not be in `registered`.
    fakes.register_result[1] = False
    pump = global_hotkey.GlobalHotkeys()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", lambda: None)})
        assert fakes.registered == {}
    finally:
        pump.stop()


def test_set_bindings_replaces_previous_registration(fakes):
    pump = global_hotkey.GlobalHotkeys()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", lambda: None)})
        first_id = next(iter(fakes.registered))

        pump.set_bindings({"video": ("ctrl+alt+2", lambda: None)})
        assert first_id in fakes.unregistered  # old combo torn down
        assert len(fakes.registered) == 1
        _, vk = next(iter(fakes.registered.values()))
        assert vk == 0x32  # new combo, not the old one
    finally:
        pump.stop()


def test_set_bindings_empty_stops_pump_and_unregisters(fakes):
    pump = global_hotkey.GlobalHotkeys()
    pump.set_bindings({"video": ("ctrl+alt+1", lambda: None)})
    hotkey_id = next(iter(fakes.registered))

    pump.set_bindings({})

    assert hotkey_id in fakes.unregistered
    assert pump._thread is None


def test_stop_without_prior_bindings_is_a_noop(fakes):
    pump = global_hotkey.GlobalHotkeys()
    pump.stop()  # must not raise
    assert fakes.unregistered == []


def test_callback_exception_is_swallowed_and_pump_keeps_running(fakes):
    def _boom():
        raise RuntimeError("boom")

    pump = global_hotkey.GlobalHotkeys()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", _boom)})
        hotkey_id = next(iter(fakes.registered))
        fakes.PostThreadMessageW(pump._thread_id, global_hotkey.WM_HOTKEY, hotkey_id, 0)
        # The pump thread must survive a raising callback -- prove it's still
        # alive and responsive by cleanly stopping it afterward.
        assert pump._thread.join(timeout=0.5) is None
        assert pump._thread.is_alive()
    finally:
        pump.stop()
    assert pump._thread is None


def test_unmatched_hotkey_id_is_ignored(fakes):
    pump = global_hotkey.GlobalHotkeys()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", lambda: None)})
        # An id nothing is bound to (e.g. a stale message) must not crash the loop.
        fakes.PostThreadMessageW(pump._thread_id, global_hotkey.WM_HOTKEY, 9999, 0)
    finally:
        pump.stop()
    assert pump._thread is None  # loop kept going and shut down cleanly


def test_non_hotkey_message_is_ignored_and_pump_keeps_pumping(fakes):
    pump = global_hotkey.GlobalHotkeys()
    try:
        pump.set_bindings({"video": ("ctrl+alt+1", lambda: None)})
        # Some other message arrives on the thread queue (e.g. WM_TIMER) --
        # must be ignored, not mistaken for WM_HOTKEY or WM_QUIT.
        fakes.PostThreadMessageW(pump._thread_id, 0x0113, 0, 0)
    finally:
        pump.stop()
    assert pump._thread is None  # stop() still worked after the stray message


def test_unregisterhotkey_failure_on_teardown_is_swallowed(fakes):
    def _raising_unregister(hwnd, hotkey_id):
        raise OSError("device removed mid-teardown")

    pump = global_hotkey.GlobalHotkeys()
    pump.set_bindings({"video": ("ctrl+alt+1", lambda: None)})
    fakes.UnregisterHotKey = _raising_unregister
    pump.stop()  # must not raise even though UnregisterHotKey blew up
    assert pump._thread is None


def test_module_level_helpers_delegate_to_the_shared_pump(fakes):
    fired = threading.Event()
    try:
        global_hotkey.set_bindings({"video": ("ctrl+alt+1", fired.set)})
        assert len(fakes.registered) == 1
        hotkey_id = next(iter(fakes.registered))
        fakes.PostThreadMessageW(global_hotkey._pump._thread_id, global_hotkey.WM_HOTKEY, hotkey_id, 0)
        assert fired.wait(2.0)
    finally:
        global_hotkey.stop()
    assert global_hotkey._pump._thread is None
