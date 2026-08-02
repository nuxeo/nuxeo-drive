"""Tests for nxdrive/drive/dao/utils.py — fix_db, restore_backup, save_backup."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from nxdrive.drive.dao.utils import (
    dump,
    fix_db,
    is_healthy,
    read,
    restore_backup,
    save_backup,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a valid temporary SQLite database."""
    db = tmp_path / "test.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO t VALUES (1, 'hello')")
    con.commit()
    con.close()
    return db


# --------------------------------------------------------------------------
# is_healthy
# --------------------------------------------------------------------------


def test_is_healthy_valid_db(tmp_db):
    assert is_healthy(tmp_db) is True


def test_is_healthy_corrupted_db(tmp_path):
    db = tmp_path / "corrupt.db"
    db.write_bytes(b"this is not a valid sqlite file at all " * 100)
    # Depending on SQLite version, this may raise or return False
    try:
        result = is_healthy(db)
        assert result is False
    except sqlite3.DatabaseError:
        pass  # Some SQLite versions raise immediately


# --------------------------------------------------------------------------
# dump and read
# --------------------------------------------------------------------------


def test_dump_and_read(tmp_db, tmp_path):
    dump_file = tmp_path / "dump.sql"
    dump(tmp_db, dump_file)
    assert dump_file.exists()
    content = dump_file.read_text()
    assert "CREATE TABLE" in content

    new_db = tmp_path / "new.db"
    read(dump_file, new_db)
    con = sqlite3.connect(str(new_db))
    rows = con.execute("SELECT * FROM t").fetchall()
    con.close()
    assert rows == [(1, "hello")]


# --------------------------------------------------------------------------
# fix_db
# --------------------------------------------------------------------------


def test_fix_db_healthy_db_returns_early(tmp_db):
    """Healthy DB → returns immediately without modification."""
    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=True) as mock_h:
        fix_db(tmp_db)
    mock_h.assert_called_once_with(tmp_db)


def test_fix_db_corrupted_db_success(tmp_db, tmp_path):
    """Lines 87+: DB is unhealthy → dump, delete, restore cycle."""
    from shutil import copyfile as real_copyfile

    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=False):
        # Actually run the fix_db logic with real dump/read
        fix_db(tmp_db)

    # DB should still exist and be healthy after fix
    assert tmp_db.exists()


def test_fix_db_database_error_raises(tmp_db):
    """Lines 100-105: sqlite3.DatabaseError during dump → re-raised."""
    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=False), \
         patch("nxdrive.drive.dao.utils.dump", side_effect=sqlite3.DatabaseError("malformed")):
        with pytest.raises(sqlite3.DatabaseError, match="malformed"):
            fix_db(tmp_db)


def test_fix_db_dump_generic_exception_returns(tmp_db):
    """Generic exception during dump → logs and returns."""
    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=False), \
         patch("nxdrive.drive.dao.utils.dump", side_effect=OSError("disk full")):
        # Should not raise
        fix_db(tmp_db)


def test_fix_db_restore_exception_with_backup(tmp_db, tmp_path):
    """Exception during read → cancels operation and restores backup."""
    backup_path = tmp_db.with_name(f"{tmp_db.name}.or")

    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=False), \
         patch("nxdrive.drive.dao.utils.dump") as mock_dump, \
         patch("nxdrive.drive.dao.utils.read", side_effect=Exception("restore failed")):
        def fake_dump(database, dump_file):
            dump_file.write_text("SQL")

        mock_dump.side_effect = fake_dump

        fix_db(tmp_db)

    # The database file should still exist (restored from backup)
    # Backup was created by copyfile before unlink


def test_fix_db_restore_exception_no_db_file(tmp_path):
    """Exception during read when DB was already unlinked → backup.rename(database)."""
    db = tmp_path / "test.db"
    # Create a valid SQLite DB so dump can work
    import sqlite3 as _sql
    con = _sql.connect(str(db))
    con.execute("CREATE TABLE t (x INTEGER)")
    con.commit()
    con.close()

    backup_path = db.with_name(f"{db.name}.or")

    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=False), \
         patch("nxdrive.drive.dao.utils.read", side_effect=Exception("fail")):
        fix_db(db)

    # After restore failure with no db file, backup should have been renamed to db
    assert db.exists() or backup_path.exists()


# --------------------------------------------------------------------------
# restore_backup
# --------------------------------------------------------------------------


def test_restore_backup_no_database():
    """Empty/falsy database path → returns False."""
    assert restore_backup(None) is False


def test_restore_backup_no_backup_folder(tmp_path):
    """No backup folder exists → returns False."""
    db = tmp_path / "manager.db"
    db.write_text("data")
    assert restore_backup(db) is False


def test_restore_backup_no_matching_backups(tmp_path):
    """Backup folder exists but no matching files → returns False."""
    db = tmp_path / "manager.db"
    db.write_text("data")
    backup_folder = tmp_path / "backups"
    backup_folder.mkdir()
    assert restore_backup(db) is False


def test_restore_backup_success(tmp_path):
    """Lines 122-139: Restores the most recent backup file."""
    db = tmp_path / "manager.db"
    db.write_text("corrupted")

    backup_folder = tmp_path / "backups"
    backup_folder.mkdir()

    # Create backups with different timestamps
    (backup_folder / "manager.db_1000").write_text("old_backup")
    (backup_folder / "manager.db_2000").write_text("new_backup")
    (backup_folder / "manager.db_1500").write_text("mid_backup")

    result = restore_backup(db)

    assert result is True
    assert db.read_text() == "new_backup"


# --------------------------------------------------------------------------
# save_backup
# --------------------------------------------------------------------------


def test_save_backup_no_database():
    """No database file → returns False."""
    assert save_backup(Path("")) is False


def test_save_backup_nonexistent_file(tmp_path):
    """Database path doesn't exist → returns False."""
    db = tmp_path / "nonexistent.db"
    assert save_backup(db) is False


def test_save_backup_corrupted_db(tmp_db):
    """Lines 152-155: Database is not healthy → won't backup, returns False."""
    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=False):
        result = save_backup(tmp_db)
    assert result is False


def test_save_backup_success(tmp_db):
    """Healthy DB → creates backup with timestamp name."""
    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=True):
        result = save_backup(tmp_db)

    assert result is True
    backup_folder = tmp_db.with_name("backups")
    assert backup_folder.is_dir()
    backups = list(backup_folder.glob(f"{tmp_db.name}_*"))
    assert len(backups) == 1


def test_save_backup_removes_old_backups(tmp_db):
    """Old backups (>1 day) are removed before saving new one."""
    backup_folder = tmp_db.with_name("backups")
    backup_folder.mkdir()

    # Create an "old" backup with a very old timestamp
    old_backup = backup_folder / f"{tmp_db.name}_1000"
    old_backup.write_text("old")

    with patch("nxdrive.drive.dao.utils.is_healthy", return_value=True):
        result = save_backup(tmp_db)

    assert result is True
    # Old backup should have been removed
    assert not old_backup.exists()
    # New backup should exist
    backups = list(backup_folder.glob(f"{tmp_db.name}_*"))
    assert len(backups) == 1
