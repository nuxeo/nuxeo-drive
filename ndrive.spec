# -*- mode: python -*-

import os
import os.path
import sys

cwd = os.getcwd()
tools = os.path.join(cwd, 'tools')
nxdrive = os.path.join(cwd, 'nuxeo-drive-client', 'nxdrive')
data = os.path.join(nxdrive, 'data')
icon = {
    'darwin': os.path.join(tools, 'osx', 'app_icon.icns'),
    'linux2': os.path.join(tools, 'linux', 'app_icon.png'),
    'win32': os.path.join(tools, 'windows', 'app_icon.ico'),
    }[sys.platform]

block_cipher = None

excludes = [
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-remove-tkinter-tcl
    'FixTk', 'tcl', 'tk', '_tkinter', 'tkinter', 'Tkinter',
]

a = Analysis([os.path.join(nxdrive, 'commandline.py')],
             pathex=[cwd],
             binaries=[],
             datas=[(data, 'data')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=excludes,
             win_no_prefer_redirects=False,
             win_private_assemblies=True,
             cipher=block_cipher)

if sys.platform == 'win32':
    # Missing OpenSSL DLLs
    a.datas += [('libeay32.dll', tools + '\windows\libeay32.dll', 'DATA')]
    a.datas += [('ssleay32.dll', tools + '\windows\ssleay32.dll', 'DATA')]

pyz = PYZ(a.pure, a.zipped_data,
          cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='ndrive',
          debug=False,
          strip=False,
          upx=False,
          console=False,
          icon=icon)

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               name='ndrive')

app = BUNDLE(coll,
             name='Nuxeo Drive.app',
             icon=icon,
             bundle_identifier='org.nuxeo.drive')
