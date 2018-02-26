# coding: utf-8
import glob
import io
import os
import re

import setuptools


def package_files(folder=os.path.join('nxdrive', 'data')):
    """ Recursively find all data files. """

    return [path for directory in os.walk(folder)
            for path in glob.glob(os.path.join(directory[0], '*'))]


def packages():
    """ Complete packages list. """

    return [
        'nxdrive',
        'nxdrive.client',
        'nxdrive.debug.wui',
        'nxdrive.gui',
        'nxdrive.osi',
        'nxdrive.osi.darwin',
        'nxdrive.osi.windows',
        'nxdrive.wui',
    ]


def version(folder='nxdrive', init_file='__init__.py'):
    """ Find the current version. """

    path = os.path.join(folder, init_file)
    with io.open(path, encoding='utf-8') as handler:
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
        description='Desktop synchronization client for Nuxeo (',
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
        packages=packages(),
        package_files={'': package_files()},
        zip_safe=False
    )


if __name__ == '__main__':
    exit(main())
