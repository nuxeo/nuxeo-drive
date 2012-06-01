#! /usr/bin/env python
#
# Copyright (C) 2012 Nuxeo
#
from distutils.core import setup

setup(
    name='nuxeo-drive',
    version='0.1.0-git',
    description="Desktop synchronization client for Nuxeo.",
    author="Olivier Grisel",
    author_email="ogrisel@nuxeo.com",
    url='http://github.com/nuxeo/nuxeo-drive',
    packages=['nxdrive'],
    scripts=["bin/nxdrive"],
    long_description=open('README.rst').read(),
)
