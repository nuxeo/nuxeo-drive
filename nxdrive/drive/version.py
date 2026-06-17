"""Version comparison utilities.

These are self-contained functions that do not depend on any
external client library.
"""

from functools import lru_cache

from packaging.version import Version


def _cmp(a, b):
    if str(a) == "0":
        return 0 if str(b) == "0" else -1
    return 1 if str(b) == "0" else (a > b) - (a < b)


@lru_cache(maxsize=128)
def version_compare(x, y):
    # type: (str, str) -> int
    # Handle None values
    if x == y == "0":
        return _cmp(x, y)

    ret = (-1, 1)

    x_numbers = x.split(".")
    y_numbers = y.split(".")
    while x_numbers and y_numbers:
        x_part = x_numbers.pop(0)
        y_part = y_numbers.pop(0)

        # Handle hotfixes
        if "HF" in x_part:
            hf = x_part.replace("-HF", ".").split(".", 1)
            x_part = hf[0]
            x_numbers.append(hf[1])
        if "HF" in y_part:
            hf = y_part.replace("-HF", ".").split(".", 1)
            y_part = hf[0]
            y_numbers.append(hf[1])

        # Handle snapshots
        x_snapshot = "SNAPSHOT" in x_part
        y_snapshot = "SNAPSHOT" in y_part
        if not x_snapshot and y_snapshot:
            x_number = int(x_part)
            y_number = int(y_part.replace("-SNAPSHOT", ""))
            return ret[y_number <= x_number]
        elif not y_snapshot and x_snapshot:
            x_number = int(x_part.replace("-SNAPSHOT", ""))
            y_number = int(y_part)
            return ret[x_number > y_number]

        x_number = int(x_part.replace("-SNAPSHOT", ""))
        y_number = int(y_part.replace("-SNAPSHOT", ""))
        if x_number != y_number:
            return ret[x_number - y_number > 0]

    if x_numbers:
        return 1
    if y_numbers:
        return -1

    return 0


@lru_cache(maxsize=128)
def version_compare_client(x, y):
    # type: (str, str) -> int
    """Try to compare SemVer and fallback to version_compare on error."""
    if x is None:
        x = "0"
    if y is None:
        y = "0"

    if x and "-I" in x:
        x = x.split("-")[0]
    if y and "-I" in y:
        y = y.split("-")[0]

    try:
        return _cmp(Version(x), Version(y))
    except Exception:
        return version_compare(x, y)


@lru_cache(maxsize=128)
def version_le(x, y):
    # type: (str, str) -> bool
    """x <= y"""
    return version_compare_client(x, y) <= 0


@lru_cache(maxsize=128)
def version_lt(x, y):
    # type: (str, str) -> bool
    """x < y"""
    return version_compare_client(x, y) < 0
