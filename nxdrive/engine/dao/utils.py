# coding: utf-8
import os
import os.path
import sqlite3
from contextlib import suppress
from logging import getLogger
from shutil import copyfile

__all__ = ("fix_db",)

log = getLogger(__name__)


def is_healthy(database: str) -> bool:
    """
    Integrity check of the entire database.
    http://www.sqlite.org/pragma.html#pragma_integrity_check
    """

    log.info("Checking database integrity: %r", database)
    with sqlite3.connect(database) as con:
        status = con.cursor().execute("PRAGMA integrity_check(1)").fetchone()
        return status[0] == "ok"


def dump(database: str, dump_file: str) -> None:
    """
    Dump the entire database content into `dump_file`.
    This function provides the same capabilities as the .dump command
    in the sqlite3 shell.
    """

    log.debug("Dumping the database %r into %r ...", database, dump_file)
    with sqlite3.connect(database) as con, open(dump_file, "w") as f:
        for line in con.iterdump():
            f.write("%s\n" % line)
    log.debug("Dump finished with success.")


def read(dump_file: str, database: str) -> None:
    """
    Load the `dump_file` content into the given database.
    This function provides the same capabilities as the .read command
    in the sqlite3 shell.
    """

    log.debug("Restoring %r into the database %r ...", dump_file, database)
    with sqlite3.connect(database) as con, open(dump_file) as f:
        con.executescript(f.read())
    log.debug("Restoration done with success.")


def fix_db(database: str, dump_file: str = "dump.sql") -> None:
    """
    Re-generate the whole database content to fix eventual FS corruptions.
    This will prevent `sqlite3.DatabaseError: database disk image is malformed`
    issues.  The whole operation is quick and help saving disk space.

        >>> fix_db('ndrive_6bba111e18ba11e89cfd180373b6442e.db')

    Will raise sqlite3.DatabaseError in case of unrecoverable file.
    """

    if is_healthy(database):
        return

    log.debug("Re-generating the whole database content of %r ...", database)

    # Dump
    try:
        old_size = os.stat(database).st_size
        backup = database + ".or"
        dump(database, dump_file)
        copyfile(database, backup)
        os.remove(database)
    except sqlite3.DatabaseError:
        # The file is so damaged we cannot save anything.
        # Forward the exception, and sorry for you :/
        log.error("Database is not recoverable")
        raise
    except:
        log.exception("Dump error")
        return

    # Restore
    try:
        read(dump_file, database)
        os.remove(backup)
    except:
        log.exception("Restoration error")
        log.info("Cancelling the operation")
        if not os.path.isfile(database):
            os.rename(backup, database)
        return
    finally:
        with suppress(OSError):
            os.remove(dump_file)

    new_size = os.stat(database).st_size
    log.debug("Re-generation completed, saved %d Kb.", (old_size - new_size) / 1024)
