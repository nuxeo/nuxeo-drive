"""
This script allows the user to check that the pytest cache folder contains
a valid lastfailed file. Will return 1 if the cache file is not found or if
no test failed. Else return 0.
"""

import json
import sys
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def run_check() -> int:
    """Open the lastfailed file and check its content."""

    last_failed_file = Path(".pytest_cache/v/cache/lastfailed")

    try:
        data = json.loads(last_failed_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(">>> No lastfailed cache file.", flush=True)
        return EXIT_FAILURE

    for _, value in data.items():
        if value:
            print(">>> Failure found.", flush=True)
            return EXIT_SUCCESS

    print(">>> No failure found.", flush=True)
    return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(run_check())
