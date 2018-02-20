# coding: utf-8
import io
import glob
import re
import setuptools
import os


def data_files(folder='nxdrive'):
    """ Recursively find all files in a given folder. """

    return [path for directory in os.walk(folder)
            for path in glob.glob(os.path.join(directory[0], '*'))]


def version(init_file='nxdrive/__init__.py'):
    """ Find the current version. """

    with io.open(init_file, encoding='utf-8') as handler:
        for line in handler.readlines():
            if line.startswith('__version__'):
                return re.findall(r"'(.+)'", line)[0]


setuptools.setup(
    name='nuxeo-drive',
    version=version(),
    author='Nuxeo',
    author_email='maintainers-python@nuxeo.com',
    url='https://github.com/nuxeo/nuxeo-drive',
    description='Desktop synchronization client for Nuxeo (',
    long_description=open(os.path.join('..', 'README.md')).read(),
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
    packages=['nxdrive'],
    data_files=data_files(),
    zip_safe=False
)
