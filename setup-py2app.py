"""
Usage:
    python setup.py py2app
"""
import sys
from distutils.core import setup
if sys.platform == 'darwin':
    import py2app  # install the py2app command

setup(
    app=["nuxeo-drive-client/bin/ndrive.py"],
    data_files=[],
    options=dict(
        py2app=dict(
            argv_emulation=True,
            plist=dict(
                CFBundleDisplayName="Nuxeo Drive",
                CFBundleName="Nuxeo Drive",
                CFBundleIdentifier="org.nuxeo.drive",
                LSUIElement=True,  # Do not launch as a Dock application
                CFBundleURLTypes=[
                    dict(
                        CFBundleURLName='Nuxeo Drive URL',
                        CFBundleURLSchemes=['nxdrive'],
                        )
                    ]
                ),
            includes=[
                "PySide",
                "PySide.QtCore",
                "PySide.QtNetwork",
                "PySide.QtGui",
                "atexit",  # implicitly required by PySide
                'sqlalchemy.dialects.sqlite',
            ]))
)
