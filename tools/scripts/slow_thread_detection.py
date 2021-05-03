""" Detect slow threads. """

import re
from datetime import datetime
from os.path import isfile
from sys import argv

__version__ = "0.1.0"


def timer(fname, delay=None):
    """
    Compute times between all lines in a given log file.

    :param fname: The log file name
    :param delay: Ignore times below this delay (seconds)
    :return: Status
    """

    if not isfile(fname):
        print("Inexistent file or wrong rights on", fname)
        return 3

    delay = delay or 2

    with open(fname) as handler:
        lines = handler.readlines()

    # First, sort log lines by thread
    regexp = re.compile(r".* (\d{15}) .*")
    threads_ = {}
    for line in lines:
        thread_ = re.findall(regexp, line)
        if not thread_:
            continue
        thread_ = thread_[0]
        try:
            threads_[thread_].append(line.strip())
        except KeyError:
            threads_[thread_] = [line.strip()]

    # Then, compute times for each lines
    regexp = re.compile(r".*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} .*")
    date_fmt = "%Y-%m-%d %H:%M:%S"
    for thread_, lines in threads_.items():
        out = ["Thread " + thread_]
        for line1, line2 in zip(lines[:-1], lines[1:]):
            time1 = datetime.strptime(re.findall(regexp, line1)[0], date_fmt)
            time2 = datetime.strptime(re.findall(regexp, line2)[0], date_fmt)
            delta = time2 - time1
            if delta.seconds < delay:
                continue
            out += [
                "        {line1}\n{delta} {line2}".format(
                    delta=delta, line1=line1, line2=line2
                )
            ]
        if len(out) > 1:
            print("\n".join(out))


def main():
    """Arguments traitment."""

    try:
        fname = argv[1]
    except IndexError:
        print("Usage: python", argv[0], "FILE [--delay=DELAY]")
        return 1
    else:
        try:
            delay = int(argv[2].split("=")[1])
        except (IndexError, ValueError):
            delay = None
        return timer(fname, delay=delay)


if __name__ == "__main__":
    exit(main())
