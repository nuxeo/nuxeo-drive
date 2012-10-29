"""
Usage:
    python setup.py py2app
"""
#from distutils.core import setup
from setuptools import setup

plist = dict(
    CFBundleDisplayName="Nuxeo Drive",
    #CFBundleName="Nuxeo Drive",
    CFBundleIdentifier="org.nuxeo.drive",
    #LSBackgroundOnly=True,
    LSUIElement=True,
    CFBundleURLTypes=[
        dict(
            CFBundleURLName='Nuxeo Drive URL',
            CFBundleURLSchemes=['nxdrive'],
        )
    ]
)
setup(
    app=["nuxeo-drive-client/bin/ndrive.py"],
    data_files=[],
    options=dict(
        py2app=dict(
            argv_emulation=True,
            plist=plist,
            includes=[
                "Foundation",
                "objc",
                "PySide",
                "PySide.QtCore",
                "PySide.QtNetwork",
                "PySide.QtGui",
                "atexit",  # implicitly required by PySide
                'sqlalchemy.dialects.sqlite']))
)
