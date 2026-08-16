"""Importing a terms list from a file merges into the existing box instead of
overwriting it, so a user's own manually-typed entries survive."""

from app.webui import Bridge


class _FakeWindow:
    def __init__(self, selection=None, raises=False):
        self._selection = selection
        self._raises = raises
        self.dialog_type = None

    def create_file_dialog(self, dialog_type, **kwargs):
        self.dialog_type = dialog_type
        if self._raises:
            raise RuntimeError("dialog blew up")
        return self._selection


def _bridge(window):
    bridge = Bridge.__new__(Bridge)
    bridge.cfg = {"beta": {"hotwords": "Existing"}}
    bridge._main_window = window
    bridge._save_cfg = lambda: True
    bridge._maybe_restart = lambda: None
    return bridge


def test_import_merges_with_existing_terms(tmp_path):
    f = tmp_path / "terms.txt"
    f.write_text("Imported1\nImported2\n", encoding="utf-8")
    bridge = _bridge(_FakeWindow(selection=[str(f)]))

    result = bridge.import_terms_file()

    assert result["ok"] is True
    assert "Existing" in result["text"]
    assert "Imported1" in result["text"]
    assert "Imported2" in result["text"]
    assert bridge.cfg["beta"]["hotwords"] == result["text"]


def test_import_cancelled_dialog_is_a_no_op():
    bridge = _bridge(_FakeWindow(selection=None))
    result = bridge.import_terms_file()
    assert result == {"ok": False, "cancelled": True}
    assert bridge.cfg["beta"]["hotwords"] == "Existing"


def test_import_without_a_window_fails_closed():
    bridge = _bridge(None)
    result = bridge.import_terms_file()
    assert result == {"ok": False, "error": "no_window"}


def test_import_dialog_exception_is_caught():
    bridge = _bridge(_FakeWindow(raises=True))
    result = bridge.import_terms_file()
    assert result == {"ok": False, "error": "dialog_failed"}


def test_import_unreadable_file_reports_error(tmp_path):
    missing = tmp_path / "does-not-exist.txt"
    bridge = _bridge(_FakeWindow(selection=[str(missing)]))
    result = bridge.import_terms_file()
    assert result == {"ok": False, "error": "read_failed"}
