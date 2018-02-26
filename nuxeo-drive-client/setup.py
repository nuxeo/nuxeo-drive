# coding: utf-8
import io
import os
import re

import setuptools


def data_files(folder='nxdrive/data'):
    """
    Find all data files.  Return appropriate sturture for `data_files=`:
        [
        ('i18n', [files]),
        ('theme', [files]),
        ('theme.default', [files]),
        ...
        ]

    """

    paths = []
    for directory, _, files in os.walk(folder):
        if not files:
            continue
        files = [directory + '/' + filename for filename in files]
        paths.append((os.path.basename(directory), files))
    return paths


def version(init_file='nxdrive/__init__.py'):
    """ Find the current version. """

    with io.open(init_file, encoding='utf-8') as handler:
        for line in handler.readlines():
            if line.startswith('__version__'):
                return re.findall(r"'(.+)'", line)[0]


def main():
    setuptools.setup(
        name='nuxeo-drive',
        version=version(),
        author='Nuxeo',
        author_email='maintainers-python@nuxeo.com',
        url='https://github.com/nuxeo/nuxeo-drive',
        description='Desktop synchronization client for Nuxeo',
        long_description='',
        license='LGPLv2+',
        classifiers=[
            'Development Status :: 5 - Production/Stable',
            'Intended Audience :: Developers',
            'Operating System :: MacOS',
            'Operating System :: MacOS :: MacOS X',
            'Operating System :: Microsoft',
            'Operating System :: Microsoft :: Windows',
            'Operating System :: Microsoft :: Windows :: Windows 7',
            'Operating System :: Microsoft :: Windows :: Windows 8',
            'Operating System :: Microsoft :: Windows :: Windows 8.1',
            'Operating System :: Microsoft :: Windows :: Windows 10',
            'Operating System :: POSIX :: Linux',
            'Programming Language :: Python',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
            'Topic :: Communications :: File Sharing',
        ],
        entry_points={
            'gui_scripts': ['ndrive=nxdrive.commandline:main'],
        },
        platforms=['Darwin', 'Linux', 'Windows'],
        packages=setuptools.find_packages(exclude=['tests']),
        data_files=data_files(),
        #include_package_data=True,
        zip_safe=False,
    )


if __name__ == '__main__':
    exit(main())
