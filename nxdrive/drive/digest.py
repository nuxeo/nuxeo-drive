"""
Digest, version comparison, and MIME-type utilities.

These are pure utility functions copied from ``nuxeo.utils`` so that
the common *drive* layer does not depend on the ``nuxeo`` Python package.
"""

import hashlib
import mimetypes
import sys
from functools import lru_cache
from typing import Optional

from _hashlib import HASH
from packaging.version import Version

__all__ = (
    "get_digest_algorithm",
    "get_digest_hash",
    "guess_mimetype",
    "version_compare",
    "version_compare_client",
    "version_le",
    "version_lt",
)

# ── Digest helpers ──────────────────────────────────────────────────────

_DIGESTERS = {
    32: "md5",
    40: "sha1",
    56: "sha224",
    64: "sha256",
    96: "sha384",
    128: "sha512",
}


def get_digest_algorithm(digest: str) -> Optional[str]:
    """Return the hash algorithm name for *digest*, or ``None``."""
    try:
        int(digest, 16) >= 0
    except (TypeError, ValueError):
        return None
    return _DIGESTERS.get(len(digest), None)


def get_digest_hash(algorithm: str) -> Optional[HASH]:
    """Return a fresh hashlib object for *algorithm*, or ``None``."""
    func = getattr(hashlib, algorithm, None)
    return func() if func else None


# ── Version comparison ──────────────────────────────────────────────────


def _cmp(a, b):
    if str(a) == "0":
        return 0 if str(b) == "0" else -1
    return 1 if str(b) == "0" else (a > b) - (a < b)


@lru_cache(maxsize=128)
def version_compare(x: str, y: str) -> int:
    """Compare two dot-separated version strings. Return -1, 0 or 1."""
    if x == y == "0":
        return _cmp(x, y)

    ret = (-1, 1)

    x_numbers = x.split(".")
    y_numbers = y.split(".")
    while x_numbers and y_numbers:
        x_part = x_numbers.pop(0)
        y_part = y_numbers.pop(0)

        if "HF" in x_part:
            hf = x_part.replace("-HF", ".").split(".", 1)
            x_part = hf[0]
            x_numbers.append(hf[1])
        if "HF" in y_part:
            hf = y_part.replace("-HF", ".").split(".", 1)
            y_part = hf[0]
            y_numbers.append(hf[1])

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
def version_compare_client(x: str, y: str) -> int:
    """Compare SemVer strings, with fallback to ``version_compare``."""
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
def version_lt(x: str, y: str) -> bool:
    """Return ``True`` if *x* < *y*."""
    return version_compare_client(x, y) < 0


@lru_cache(maxsize=128)
def version_le(x: str, y: str) -> bool:
    """Return ``True`` if *x* <= *y*."""
    return version_compare_client(x, y) <= 0


# ── MIME-type guessing ──────────────────────────────────────────────────

_WIN32_PATCHED_MIME_TYPES = {
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
    "image/bmp": "image/x-ms-bmp",
    "audio/x-mpg": "audio/mpeg",
    "video/x-mpeg2a": "video/mpeg",
    "application/x-javascript": "application/javascript",
    "application/x-msexcel": "application/vnd.ms-excel",
    "application/x-mspowerpoint": "application/vnd.ms-powerpoint",
    "application/x-mspowerpoint.12": (
        "application/vnd.openxmlformats-officedocument" ".presentationml.presentation"
    ),
}


def guess_mimetype(filename: str) -> str:
    """Guess the MIME type of *filename*."""
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if sys.platform == "win32":
            mime_type = _WIN32_PATCHED_MIME_TYPES.get(mime_type, mime_type)
        return mime_type
    return "application/octet-stream"
