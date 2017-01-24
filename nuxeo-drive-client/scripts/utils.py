# coding: utf-8
from inspect import getsourcefile
from os.path import abspath, dirname


def module_path():
    """ Find the absolute path of the current module.

    :return: str Absolute path of the current module
    """
    return dirname(abspath(getsourcefile(lambda: 0)))
