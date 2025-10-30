import plistlib
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from nxdrive.updater.darwin import Updater


def make_updater():
    """Create an Updater without running BaseUpdater.__init__ (avoids Qt threads)."""
    # Use the class __new__ which is safe for this type
    upd = Updater.__new__(Updater)
    upd.manager = SimpleNamespace(osi=SimpleNamespace(cleanup=lambda: None))
    return upd


def test_mount_parses_plist(monkeypatch, tmp_path):
    # Prepare a fake plist output similar to hdiutil -plist
    data = {
        "system-entities": [
            {"potentially-mountable": False},
            {
                "potentially-mountable": True,
                "dev-entry": "/dev/disk2s1",
                "mount-point": "/Volumes/Nuxeo Drive",
            },
        ]
    }

    expected_cmd = ["hdiutil", "mount", "-plist", "some.dmg"]

    def fake_check_output(cmd):
        assert cmd == expected_cmd
        return plistlib.dumps(data)

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    u = make_updater()
    mount = u._mount("some.dmg")
    assert mount == "/Volumes/Nuxeo Drive"


def test_unmount_handles_calledprocesserror(monkeypatch):
    called = {}

    def fake_check_call(cmd):
        called["cmd"] = cmd
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    u = make_updater()
    # Should not raise despite CalledProcessError
    u._unmount("/Volumes/X")
    assert called["cmd"][0] == "hdiutil"


def test_backup_and_restore(tmp_path):
    # Create a fake .app directory
    src = tmp_path / "My.app"
    src.mkdir()

    u = make_updater()
    u.final_app = src

    # Backup: should move My.app -> My.app.old
    u._backup()
    dst = tmp_path / "My.app.old"
    assert dst.exists()
    assert not src.exists()

    # Restore: move My.app.old -> My.app
    u._backup(restore=True)
    assert src.exists()
    assert not dst.exists()


def test_cleanup_removes_paths(tmp_path):
    final = tmp_path / "App.app"
    final.mkdir()
    # Create .old dir and an installer dir to be removed
    old = Path(f"{final}.old")
    old.mkdir()
    inst = tmp_path / "installer.dmg"
    inst.mkdir()

    u = make_updater()
    u.final_app = final

    u._cleanup(str(inst))
    assert not old.exists()
    assert not inst.exists()


def test_copy_calls_ditto_and_propagates_error(monkeypatch, tmp_path):
    # Prepare a fake mount dir with the expected app bundle
    mount_dir = tmp_path / "mount"
    app_bundle = mount_dir / "Nuxeo Drive.app"
    app_bundle.mkdir(parents=True)

    dest = tmp_path / "Final.app"

    u = make_updater()
    u.final_app = dest

    recorded = {}

    def fake_check_call(cmd):
        recorded["cmd"] = cmd

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    # Success path: should call ditto with src and dest
    u._copy(str(mount_dir))
    assert recorded["cmd"][0] == 'ditto'
    # On Windows the darwin code builds the src with a forward slash
    # so compare by app bundle name rather than full path
    assert 'Nuxeo Drive.app' in recorded["cmd"][1]

    # Failure path: make check_call raise CalledProcessError and expect _copy to raise
    def failing_call(cmd):
        raise subprocess.CalledProcessError(2, cmd)

    monkeypatch.setattr(subprocess, "check_call", failing_call)
    with pytest.raises(subprocess.CalledProcessError):
        u._copy(str(mount_dir))


def test_fix_notarization_suppresses_error(monkeypatch):
    called = {}

    def raising_call(cmd):
        called["cmd"] = cmd
        raise subprocess.CalledProcessError(3, cmd)

    monkeypatch.setattr(subprocess, "check_call", raising_call)

    u = make_updater()
    # Should not raise
    u._fix_notarization("some.dmg")
    assert called["cmd"][0] == 'xattr'


def test_restart_launches_and_emits(monkeypatch):
    popped = {}

    def fake_popen(cmd, shell, close_fds):
        popped["cmd"] = cmd
        popped["shell"] = shell
        popped["close_fds"] = close_fds

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    emit_called = {}

    def fake_emit():
        emit_called["ok"] = True

    u = make_updater()
    u.final_app = Path("/Applications/Fake.app")
    # Replace the pyqtSignal with a simple object having an emit method
    u.appUpdated = SimpleNamespace(emit=fake_emit)

    u._restart()
    assert 'sleep' in popped["cmd"]
    assert popped["shell"] is True
    assert emit_called.get('ok', False) is True
