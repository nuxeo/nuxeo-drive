# coding: utf-8
"""
Find most random failures on master job.

Document: https://docs.google.com/spreadsheets/d/1aAkoZAl9etLFQvTkaxKyHSvHMOTyy22_0iGBOAbBJ0E

1. Be sure to be on the "results" sheet.
2. File > "Download as" > "Comma-separated values (.csv, current sheet)".
3. Save the CSV file to the same folder of this script.
4. CLI:

    % python common_failures.py [BUILD_NUMBER]

   Where BUILD_NUMBER is the lowest build number to check,
   ie. if BUILD_NUMBER is 42, then the script will take into
   account only builds > 42.
"""

import collections
import csv
import os
import sys

__version__ = '0.1.0'


# Error messages that are not revelant
TO_IGNORE = [
    '',
    'General timeout',
    'Not related to Drive',
    'Slave error or misconfiguration',
    'General timeout',
]


def is_valid(row, system):
    """ Chek if a given row is good to take into account. """

    return row[system] not in TO_IGNORE


def show_recurrent_randoms(file_, build_min=0):
    """ . """

    counters = collections.OrderedDict()
    counters['GNU/Linux'] = collections.Counter()
    counters['Mac'] = collections.Counter()
    counters['Windows'] = collections.Counter()
    counters['All'] = collections.Counter()
    fmt = '{count:4}: {failure}'

    with open(file_) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if int(row['Build']) > build_min:
                if is_valid(row, 'GNU/Linux'):
                    counters['GNU/Linux'].update([row['GNU/Linux']])
                if is_valid(row, 'Mac'):
                    counters['Mac'].update([row['Mac']])
                if is_valid(row, 'Windows'):
                    counters['Windows'].update([row['Windows']])

    for system, counter in counters.items():
        counter_ = collections.Counter({k: c for k, c in counter.items()
                                             if c > 1})
        if not counter_:
            continue

        print(system)
        for failure, count in counter_.most_common(5):
            print(fmt.format(failure=failure, count=count))
            counters['All'].update([failure] * count)


def main():
    """ . """

    try:
        build_min = int(sys.argv[1])
    except (IndexError, ValueError):
        build_min = 0

    default = 'Drive Jenkins master PPL - results.csv'
    input_file = os.environ.get('DRIVE_CSV', default)
    show_recurrent_randoms(input_file, build_min=build_min)


if __name__ == '__main__':
    exit(main())
