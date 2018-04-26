# -*- mode: python -*-
# coding: utf-8

import io
import os
import os.path
import re
import sys


def get_version(init_file):
    """ Find the current version. """

    with io.open(init_file, encoding='utf-8') as handler:
        for line in handler.readlines():
            if line.startswith('__version__'):
                return re.findall(r"'(.+)'", line)[0]


cwd = os.getcwd()
tools = os.path.join(cwd, 'tools')
nxdrive = os.path.join(cwd, 'nxdrive')
data = os.path.join(nxdrive, 'data')
icon = {
    'darwin': os.path.join(tools, 'osx', 'app_icon.icns'),
    'linux2': os.path.join(tools, 'linux', 'app_icon.png'),
    'win32': os.path.join(tools, 'windows', 'app_icon.ico'),
    }[sys.platform]

excludes = [
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-remove-tkinter-tcl
    'FixTk', 'tcl', 'tk', '_tkinter', 'tkinter', 'Tkinter',

    # Misc
    'PIL', 'ipdb', 'numpy', 'pydev', 'scipy', 'yappi',
]

data = [(data, 'data')]
properties_rc = None

if sys.platform == 'win32':
    # Missing OpenSSL DLLs
    data.append((tools + '\windows\libeay32.dll', 'libeay32.dll'))
    data.append((tools + '\windows\ssleay32.dll', 'ssleay32.dll'))

    # Set executable properties
    properties_tpl = tools + '\windows\properties_tpl.rc'
    properties_rc = tools + '\windows\properties.rc'
    if os.path.isfile(properties_rc):
        os.remove(properties_rc)

    version = get_version(nxdrive + '\__init__.py')
    version_tuple = tuple(map(int, version.split('.') + [0]))

    tpl = io.open(properties_tpl, encoding='utf-8')
    out = io.open(properties_rc, 'w', encoding='utf-8')
    with tpl, out:
        content = tpl.read().format(version=version,
                                    version_tuple=version_tuple)
        print(content)
        out.write(content)


a = Analysis([os.path.join(nxdrive, '__main__.py')],
             pathex=[cwd],
             datas=data,
             excludes=excludes)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='ndrive',
          console=False,
          debug=False,
          strip=False,
          upx=False,
          icon=icon,
          version=properties_rc)

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               name='ndrive')

app = BUNDLE(coll,
             name='Nuxeo Drive.app',
             icon=icon,
             bundle_identifier='org.nuxeo.drive')
