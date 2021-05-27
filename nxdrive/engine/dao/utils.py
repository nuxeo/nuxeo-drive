import sqlite3
from datetime import datetime, timedelta
from logging import getLogger
from os import fsync
from pathlib import Path
from shutil import copyfile

__all__ = ("fix_db", "restore_backup", "save_backup")

log = getLogger(__name__)


def is_healthy(database: Path, /) -> bool:
    """
    Integrity check of the entire database.
    http://www.sqlite.org/pragma.html#pragma_integrity_check
    """

    log.info(f"Checking database integrity: {database!r}")
    con = sqlite3.connect(str(database))
    try:
        status = con.execute("PRAGMA integrity_check(1)").fetchone()
        return bool(status[0] == "ok")
    finally:
        # According to the documentation:
        #   Connection object used as context manager only commits or rollbacks
        #   transactions, so the connection object should be closed manually.
        con.close()


def dump(database: Path, dump_file: Path, /) -> None:
    """
    Dump the entire database content into `dump_file`.
    This function provides the same capabilities as the .dump command
    in the sqlite3 shell.
    """

    log.info(f"Dumping the database {database!r} into {dump_file!r}...")
    with sqlite3.connect(str(database)) as con, dump_file.open(
        mode="w", encoding="utf-8"
    ) as f:
        for line in con.iterdump():
            f.write(f"{line}\n")

        # Force write of file to disk
        f.flush()
        fsync(f.fileno())

    log.info("Dump finished with success.")


def read(dump_file: Path, database: Path, /) -> None:
    """
    Load the `dump_file` content into the given database.
    This function provides the same capabilities as the .read command
    in the sqlite3 shell.
    """

    log.info(f"Restoring {dump_file!r} into the database {database!r} ...")
    with sqlite3.connect(str(database)) as con:
        con.executescript(dump_file.read_text(encoding="utf-8"))
    log.info("Restoration done with success.")


def fix_db(database: Path, /, *, dump_file: Path = Path("dump.sql")) -> None:
    """
    Re-generate the whole database content to fix eventual FS corruptions.
    This will prevent `sqlite3.DatabaseError: database disk image is malformed`
    issues.  The whole operation is quick and help saving disk space.

        >>> fix_db('ndrive_6bba111e18ba11e89cfd180373b6442e.db')

    Will raise sqlite3.DatabaseError in case of unrecoverable file.
    """

    if is_healthy(database):
        return

    log.info(f"Re-generating the whole database content of {database!r}...")

    # Dump
    try:
        old_size = database.stat().st_size
        backup = database.with_name(f"{database.name}.or")
        dump(database, dump_file)
        copyfile(str(database), str(backup))
        database.unlink()
    except sqlite3.DatabaseError:
        # The file is so damaged we cannot save anything.
        # Forward the exception, and sorry for you :/
        log.exception("Database is not recoverable")
        raise
    except Exception:
        log.exception("Dump error")
        return

    # Restore
    try:
        read(dump_file, database)
        backup.unlink()
    except Exception:
        log.exception("Restoration error")
        log.info("Cancelling the operation")
        if not database.is_file():
            backup.rename(database)
        return
    finally:
        dump_file.unlink(missing_ok=True)

    new_size = database.stat().st_size
    log.info(f"Re-generation completed, saved {(old_size - new_size) / 1024} Kb.")


def restore_backup(database: Path, /) -> bool:
    """
    Restore a backup of a given database.

    For example, if the path is ~/.nuxeo-drive/manager.db,
    it will look for all files matching ~/.nuxeo-drive/backups/manager.db_*
    and take the one with the most recent timestamp.
    """

    if not database:
        return False

    backup_folder = database.with_name("backups")
    if not backup_folder.is_dir():
        log.info("No existing backup folder")
        return False

    backups = list(backup_folder.glob(f"{database.name}_*"))
    if not backups:
        log.info(f"No backup available for {database}")
        return False

    latest = max(backups, key=lambda p: int(p.name.split("_")[-1]))
    log.info(f"Found a backup candidate, trying to restore {latest}")
    database.unlink(missing_ok=True)
    copyfile(latest, database)
    return True


def save_backup(database: Path, /) -> bool:
    """
    Save a backup of a given database.

    For example, if the path is ~/.nuxeo-drive/manager.db,
    a corresponding ~/.nuxeo-drive/backups/manager.db_1234567890 file
    will be created, where the numbers are the current timestamp.
    """

    if not (database and database.is_file()):
        log.info("No database to backup")
        return False
    if not is_healthy(database):
        log.info(f"{database} is corrupted, won't backup")
        return False

    backup_folder = database.with_name("backups")
    backup_folder.mkdir(exist_ok=True)

    yesterday = int((datetime.now() - timedelta(days=1)).timestamp())
    old_backups = [
        b
        for b in backup_folder.glob(f"{database.name}_*")
        if int(b.name.split("_")[-1]) < yesterday
    ]
    # Remove older backups
    for backup in old_backups:
        log.debug(f"Removing old backup {backup}")
        backup.unlink(missing_ok=True)

    backup = backup_folder / f"{database.name}_{int(datetime.now().timestamp())}"
    log.info(f"Creating backup {backup}")
    copyfile(database, backup)
    return True
