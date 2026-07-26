"""Pytest bootstrap: make the repo root importable so `app.*` resolves when
pytest is invoked from anywhere."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolate_diagnostic_log(tmp_path_factory, monkeypatch):
    """Keep the suite out of the developer's real voxis.log.

    `config._log_failure` and `voxis_client._log_detail` append straight to
    `user_path("voxis.log")`, which from source resolves to the REPO ROOT. Two
    tests corrupt a config on purpose (`test_corrupt_config_falls_back_to_defaults`
    writes "{ this is not json", `test_non_object_root_falls_back` writes a JSON
    array) and the client tests exercise 401/500 refresh paths -- so every run
    appended four fabricated failures to the same file real diagnostics land in.
    342 config + 338 client lines had accumulated by 2026-07-25, which is exactly
    the noise that hides a genuine error when someone greps that log.

    Redirecting the writer, not the config path, is what makes this airtight: the
    tests already point CONFIG_PATH at a tmp dir, but the LOG path is resolved
    independently and was never patched.
    """
    logdir = tmp_path_factory.mktemp("logs")
    target = str(logdir / "voxis.log")
    for module in ("app.config", "app.voxis_client"):
        try:
            mod = __import__(module, fromlist=["_logfile"])
        except Exception:
            continue
        if hasattr(mod, "_logfile"):
            monkeypatch.setattr(mod, "_logfile", lambda _t=target: _t)
    yield target
