import os
import random
import shutil
import struct
import zlib
from pathlib import Path
from time import sleep
from typing import Union

from nxdrive.utils import normalized_path, safe_long_path, unset_path_readonly


def clean_dir(_dir: Path, retry: int = 1, max_retries: int = 5) -> None:
    _dir = safe_long_path(_dir)
    if not _dir.exists():
        return

    test_data = os.environ.get("TEST_SAVE_DATA")
    if test_data:
        shutil.move(_dir, test_data)
        return

    try:
        for path, folders, filenames in os.walk(_dir):
            dirpath = normalized_path(path)
            for folder in folders:
                unset_path_readonly(dirpath / folder)
            for filename in filenames:
                unset_path_readonly(dirpath / filename)
        shutil.rmtree(_dir)
    except Exception:
        if retry < max_retries:
            sleep(2)
            clean_dir(_dir, retry=retry + 1)


def random_png(filename: Path = None, size: int = 0) -> Union[None, bytes]:
    """Generate a random PNG file.

    :param filename: The output file name. If None, returns
            the picture content.
    :param size: The number of black pixels of the picture.
    :return: None if given filename else bytes
    """

    if not size:
        size = random.randint(1, 42)
    else:
        size = max(1, size)

    pack = struct.pack

    def chunk(header, data):
        return (
            pack(">I", len(data))
            + header
            + data
            + pack(">I", zlib.crc32(header + data) & 0xFFFFFFFF)
        )

    magic = pack(">8B", 137, 80, 78, 71, 13, 10, 26, 10)
    png_filter = pack(">B", 0)
    scanline = pack(">{}B".format(size * 3), *[0] * (size * 3))
    content = [png_filter + scanline for _ in range(size)]
    png = (
        magic
        + chunk(b"IHDR", pack(">2I5B", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(content)))
        + chunk(b"IEND", b"")
    )

    if not filename:
        return png

    filename.write_bytes(png)


def salt(text: str, prefix: str = "ndt-", with_suffix: bool = True) -> str:
    """
    Add some salt to the given text to ensure no collisions.
    To use for workspace titles, usernames, groups names ...
    """
    suffix = random.randint(1, 99999) if with_suffix else ""
    return f"{prefix}{text}-{suffix}"
