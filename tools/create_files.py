# coding: utf-8
import os
import string
import sys
from random import choice, seed


def random_word():
    return "".join([choice(string.lowercase)
                    for _ in range(choice(range(4, 10)))])


def random_line(n_words=10):
    return " ".join([random_word() for _ in range(n_words)])


def random_text(n_lines=30, n_words=10):
    return "\n".join([random_line(n_words) for _ in range(n_lines)])


def make_files(n_files=100, base_folder='.'):

    for i in range(n_files):
        path = os.path.join(
            base_folder,
            "File %04d.txt" % i)
        if not os.path.exists(path):
            print("Creating file: " + path)
            open(path, 'wb').write(random_text())


if __name__ == "__main__":
    seed(42)
    base = sys.argv[1] if len(sys.argv) > 1 else '.'
    n_files = sys.argv[2] if len(sys.argv) > 2 else 100
    make_files(n_files=int(n_files), base_folder=base)
