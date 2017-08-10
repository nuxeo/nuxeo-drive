# coding: utf-8
import os
import string
import sys
from itertools import product
from random import choice, seed


def random_word():
    return "".join([choice(string.lowercase)
                    for _ in range(choice(range(4, 10)))])


def random_line(n_words=10):
    return " ".join([random_word() for _ in range(n_words)])


def random_text(n_lines=30, n_words=10):
    return "\n".join([random_line(n_words) for _ in range(n_lines)])


def make_folder_tree(n_folders=10, base_folder='.'):

    for i, j, k in product(range(n_folders), range(n_folders),
                           range(n_folders)):
        path = os.path.join(
            base_folder,
            "Folder %02d" % i,
            "Folder %02d.%02d" % (i, j),
            "Folder %02d.%02d.%02d" % (i, j, k))

        if not os.path.exists(path):
            print("Creating folder: " + path)
            os.makedirs(path)

        path = os.path.join(
            base_folder,
            "Folder %02d" % i,
            "Folder %02d.%02d" % (i, j),
            "File %02d.%02d.%02d.txt" % (i, j, k))
        if not os.path.exists(path):
            print("Creating file: " + path)
            open(path, 'wb').write(random_text())


if __name__ == "__main__":
    seed(42)
    base = sys.argv[1] if len(sys.argv) > 1 else '.'
    make_folder_tree(base_folder=base)
