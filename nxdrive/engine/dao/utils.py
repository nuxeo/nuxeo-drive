# coding: utf-8
import sqlite3
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from shutil import copyfile

__all__ = ("fix_db",)

log = getLogger(__name__)


def is_healthy(database: Path) -> bool:
    """
    Integrity check of the entire database.
    http://www.sqlite.org/pragma.html#pragma_integrity_check
    """

    log.info(f"Checking database integrity: {database!r}")
    with sqlite3.connect(str(database)) as con:
        status = con.cursor().execute("PRAGMA integrity_check(1)").fetchone()
        return status[0] == "ok"


def dump(database: Path, dump_file: Path) -> None:
    """
    Dump the entire database content into `dump_file`.
    This function provides the same capabilities as the .dump command
    in the sqlite3 shell.
    """

    log.debug(f"Dumping the database {database!r} into {dump_file!r}...")
    with sqlite3.connect(str(database)) as con, dump_file.open(mode="w") as f:
        for line in con.iterdump():
            f.write(f"{line}\n")
    log.debug("Dump finished with success.")


def read(dump_file: Path, database: Path) -> None:
    """
    Load the `dump_file` content into the given database.
    This function provides the same capabilities as the .read command
    in the sqlite3 shell.
    """

    log.debug(f"Restoring {dump_file!r} into the database {database!r} ...")
    with sqlite3.connect(str(database)) as con:
        con.executescript(dump_file.read_text())
    log.debug("Restoration done with success.")


def fix_db(database: Path, dump_file: Path = Path("dump.sql")) -> None:
    """
    Re-generate the whole database content to fix eventual FS corruptions.
    This will prevent `sqlite3.DatabaseError: database disk image is malformed`
    issues.  The whole operation is quick and help saving disk space.

        >>> fix_db('ndrive_6bba111e18ba11e89cfd180373b6442e.db')

    Will raise sqlite3.DatabaseError in case of unrecoverable file.
    """

    if is_healthy(database):
        return

    log.debug(f"Re-generating the whole database content of {database!r}...")

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
    except:
        log.exception("Dump error")
        return

    # Restore
    try:
        read(dump_file, database)
        backup.unlink()
    except:
        log.exception("Restoration error")
        log.info("Cancelling the operation")
        if not database.is_file():
            backup.rename(database)
        return
    finally:
        with suppress(OSError):
            dump_file.unlink()

    new_size = database.stat().st_size
    log.debug(f"Re-generation completed, saved {(old_size - new_size) / 1024} Kb.")
