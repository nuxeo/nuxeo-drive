"""
Convert a CSV "log" file to a real log file.
Such files are ones attached to NCO tickets.
"""
import csv
import sys
from pathlib import Path
from typing import List


def convert(file: Path) -> Path:
    """Convert a given CVS *file* to a simple log file."""
    output = file.with_suffix(".log")
    with file.open() as csvfile, output.open("w") as fout:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # date,host,message
            line = "{date} {message}\n".format(**row)
            fout.write(line)
    return output


def main(files: List[str]) -> int:
    """Handle given *files*."""
    if not files:
        print(__doc__)
        print("Usage: python", Path(sys.argv[0]).name, "FILE [FILE...]")
        return 1

    errcode = 0
    for file in files:
        try:
            output = convert(Path(file))
            print(">>>", file, "->", output)
        except Exception as exc:
            # An error should not stop the entire process
            print(" ! ", file, str(exc))
            errcode = 2

    return errcode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
