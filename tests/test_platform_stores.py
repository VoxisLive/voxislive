"""Faz 1 platform stores: at-rest crypto, device fingerprint, XDG paths.

The Linux code paths are exercised on any host by faking `sys.platform` — the
modules read it at call time, so the real Fernet wrap/unwrap, machine-id parsing
and XDG resolution run here even on the Windows dev box. Windows behaviour is
covered by asserting the existing shape is unchanged.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import byok_store, device_id, paths, secret_crypto, voxis_client

# --- secret_crypto (platform-agnostic Fernet) -------------------------------

def test_fernet_round_trip():
    ent = b"\x11" * 32
    blob = secret_crypto.fernet_encrypt(b"hello-secret", ent)
    assert blob != b"hello-secret"
    assert secret_crypto.fernet_decrypt(blob, ent) == b"hello-secret"


def test_fernet_wrong_entropy_fails():
    from cryptography.fernet import InvalidToken

    blob = secret_crypto.fernet_encrypt(b"x", b"\x11" * 32)
    with pytest.raises(InvalidToken):
        secret_crypto.fernet_decrypt(blob, b"\x22" * 32)


def test_fernet_handles_nonstandard_entropy_length():
    # A short public constant (like voxis_client._JWT_ENTROPY) must still key a
    # valid Fernet cipher (hashed to 32 bytes internally).
    ent = b"voxis-jwt-v1"
    blob = secret_crypto.fernet_encrypt(b"tok", ent)
    assert secret_crypto.fernet_decrypt(blob, ent) == b"tok"


# --- byok_store Linux (Fernet) slot round trip ------------------------------

def test_byok_fernet_slot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(byok_store, "_STORE_DIR", str(tmp_path / "byok"))
    monkeypatch.setattr(byok_store, "install_secret", lambda *a, **k: b"\x07" * 32)
    byok_store.save_byok("user-1", gemini="G-KEY")
    got = byok_store.load_byok("user-1")
    assert got == {"gemini": "G-KEY"}
    assert byok_store.has_byok("user-1", "gemini")


def test_byok_fernet_slot_on_disk_is_wrapped(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(byok_store, "_STORE_DIR", str(tmp_path / "byok"))
    monkeypatch.setattr(byok_store, "install_secret", lambda *a, **k: b"\x07" * 32)
    byok_store.save_byok("user-2", gemini="SECRET")
    raw = open(byok_store._slot_path("user-2"), "rb").read()
    assert raw.startswith(byok_store._FERNET_MAGIC)
    assert b"SECRET" not in raw


def test_install_secret_first_use_is_identical_for_concurrent_callers(
        tmp_path, monkeypatch):
    secret_path = tmp_path / "install.secret"
    monkeypatch.setattr(
        paths, "user_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    with ThreadPoolExecutor(max_workers=16) as pool:
        values = list(pool.map(lambda _: paths.install_secret(), range(32)))
    assert len(set(values)) == 1
    assert values[0] == secret_path.read_bytes()


def test_concurrent_byok_saves_do_not_share_a_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(byok_store, "_STORE_DIR", str(tmp_path / "byok"))
    monkeypatch.setattr(byok_store, "install_secret", lambda *a, **k: b"\x07" * 32)
    monkeypatch.setattr(byok_store, "_restrict_acl", lambda path: None)
    keys = [f"KEY-{i}" for i in range(24)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda key: byok_store.save_byok("same-user", gemini=key), keys))
    assert byok_store.load_byok("same-user")["gemini"] in keys
    assert not list((tmp_path / "byok").glob("*.tmp"))


# --- voxis_client Linux JWT at rest -----------------------------------------

def test_jwt_fernet_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(voxis_client, "_JWT_PATH", str(tmp_path / "jwt.dat"))
    monkeypatch.setattr(voxis_client, "_ENV_PATH", str(tmp_path / ".env"))
    monkeypatch.setattr(voxis_client, "install_secret", lambda *a, **k: b"\x09" * 32)
    voxis_client._store_jwt("my.jwt.token")
    raw = open(voxis_client._JWT_PATH, "rb").read()
    assert b"my.jwt.token" not in raw          # encrypted at rest, not cleartext
    monkeypatch.setattr(voxis_client, "_jwt", None)
    voxis_client._load_stored_jwt()
    assert voxis_client.get_jwt() == "my.jwt.token"


# --- voxis_client Windows JWT at rest (DPAPI) --------------------------------
# The Windows path used to DPAPI-wrap the JWT with a bare, hardcoded public
# constant as entropy (_JWT_ENTROPY alone) -- readable from this open-source
# file, so it added nothing beyond DPAPI's own per-user binding. _jwt_entropy()
# now mixes in install_secret() like byok_store.py already did. These run for
# real (no sys.platform fake) since DPAPI is only meaningful on actual Windows.

@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_jwt_dpapi_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(voxis_client, "_JWT_PATH", str(tmp_path / "jwt.dat"))
    monkeypatch.setattr(voxis_client, "_ENV_PATH", str(tmp_path / ".env"))
    monkeypatch.setattr(voxis_client, "install_secret", lambda *a, **k: b"\x0a" * 32)
    voxis_client._store_jwt("dpapi.jwt.token")
    raw = open(voxis_client._JWT_PATH, "rb").read()
    assert b"dpapi.jwt.token" not in raw
    monkeypatch.setattr(voxis_client, "_jwt", None)
    voxis_client._load_stored_jwt()
    assert voxis_client.get_jwt() == "dpapi.jwt.token"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_jwt_dpapi_migrates_legacy_bare_entropy_blob_on_read(tmp_path, monkeypatch):
    # Simulate a blob written by the pre-fix build: DPAPI-protected with the
    # bare public _JWT_ENTROPY constant, no install_secret mixed in.
    monkeypatch.setattr(voxis_client, "_JWT_PATH", str(tmp_path / "jwt.dat"))
    monkeypatch.setattr(voxis_client, "_ENV_PATH", str(tmp_path / ".env"))
    monkeypatch.setattr(voxis_client, "install_secret", lambda *a, **k: b"\x0b" * 32)
    legacy_blob = voxis_client._dpapi_call("CryptProtectData", b"legacy.jwt.token")
    with open(voxis_client._JWT_PATH, "wb") as f:
        f.write(legacy_blob)

    monkeypatch.setattr(voxis_client, "_jwt", None)
    voxis_client._load_stored_jwt()
    assert voxis_client.get_jwt() == "legacy.jwt.token"

    # Migrate-on-read must have rewritten the file under the new entropy: a
    # decrypt using ONLY the new entropy (no bare-entropy fallback) now works.
    raw = open(voxis_client._JWT_PATH, "rb").read()
    migrated = voxis_client._dpapi_call(
        "CryptUnprotectData", raw, voxis_client._jwt_entropy()).decode()
    assert migrated == "legacy.jwt.token"


# --- device_id Linux fingerprint --------------------------------------------

def test_linux_fingerprint_machine_id_and_dmi(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(device_id, "_cache", None)
    files = {
        "/etc/machine-id": "abc123def456\n",
        "/sys/class/dmi/id/board_serial": "BOARD-SN-9\n",
        "/sys/class/dmi/id/product_uuid": "UUID-77\n",
    }
    monkeypatch.setattr(device_id, "_read_text", lambda p: files.get(p, ""))
    fp = device_id.fingerprint()
    assert fp["primary"] == "abc123def456"
    assert fp["secondary"] == "BOARD-SN-9|UUID-77"


def test_linux_fingerprint_rpi_devicetree_fallback(monkeypatch):
    # Raspberry Pi (ARM): no DMI, serial comes from the device tree.
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(device_id, "_cache", None)
    files = {
        "/etc/machine-id": "pi-machine-id\n",
        "/proc/device-tree/serial-number": "10000000abcdef\x00",
    }
    monkeypatch.setattr(device_id, "_read_text", lambda p: files.get(p, ""))
    fp = device_id.fingerprint()
    assert fp["primary"] == "pi-machine-id"
    assert fp["secondary"] == "10000000abcdef"


# --- paths: XDG on Linux, unchanged on Windows ------------------------------

def test_user_data_dir_linux_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    p = paths.user_data_dir()
    assert p == str(tmp_path / "cfg" / "Voxis")


def test_xdg_documents_dir_fallback(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DOCUMENTS_DIR", raising=False)
    # xdg-user-dir may be absent (Windows dev box), present but returning $HOME
    # because DOCUMENTS is unconfigured (fresh Raspberry Pi OS), or present and
    # correctly resolving a LOCALIZED folder name (confirmed on a tr_TR desktop,
    # 2026-07-19: "~/Belgeler", not "~/Documents") -- so the only invariant that
    # holds across locales is "never the bare home root", not any English name.
    home = os.path.expanduser("~")
    got = paths.documents_dir()
    assert os.path.normpath(got) != os.path.normpath(home)
