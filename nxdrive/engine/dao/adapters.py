from pathlib import Path


def adapt_path(path: Path, /) -> str:
    """
    Return the string needed to work with data from the database from a given *path*.
    It is used across the whole file and also in the SQLite adapter to convert
    a Path object to str before insertion into database.

    Note: The starting forward-slash will be automatically added if not present
          and if the *path* is not absolute (Direct Transfer paths for instance).
    """
    posix_path = path.as_posix()
    # Note: ROOT.as_posix(), Path.path().as_posix(), Path.path("").as_posix() and Path(".").as_posix() will return "."
    if posix_path == ".":
        return "/"
    if posix_path[0] != "/" and not path.is_absolute():
        return f"/{posix_path}"
    return posix_path
