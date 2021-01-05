# -*- mode: python -*-
import io
import os
import os.path
import re
import sys


def get_version(init_file):
    """ Find the current version. """

    with io.open(init_file, encoding="utf-8") as handler:
        for line in handler.readlines():
            if line.startswith("__version__"):
                return re.findall(r"\"(.+)\"", line)[0]


cwd = os.getcwd()
tools = os.path.join(cwd, "tools")
nxdrive = os.path.join(cwd, "nxdrive")
data = os.path.join(nxdrive, "data")
icon = {
    "darwin": os.path.join(tools, "osx", "app_icon.icns"),
    "linux": os.path.join(tools, "linux", "app_icon.png"),
    "win32": os.path.join(tools, "windows", "app_icon.ico"),
}[sys.platform]

hiddenimports = []
excludes = [
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-remove-tkinter-tcl
    "FixTk",
    "tcl",
    "tk",
    "_tkinter",
    "tkinter",
    "Tkinter",
    # Misc
    "PIL",
    "ipdb",
    "lib2to3",
    "numpy",
    "pydev",
    "scipy",
    "yappi",
]

data = [(data, "data")]
version = get_version(os.path.join(nxdrive, "__init__.py"))
properties_rc = None

if sys.platform == "win32":
    # Set executable properties
    properties_tpl = tools + "\\windows\\properties_tpl.rc"
    properties_rc = tools + "\\windows\\properties.rc"
    if os.path.isfile(properties_rc):
        os.remove(properties_rc)

    version_tuple = tuple(map(int, version.split(".") + [0] * (3 - version.count("."))))

    with open(properties_tpl) as tpl, open(properties_rc, "w") as out:
        content = tpl.read().format(version=version, version_tuple=version_tuple)
        print(content)
        out.write(content)

    # Missing modules when packaged
    hiddenimports.append("win32timezone")

a = Analysis(
    [os.path.join(nxdrive, "__main__.py")],
    datas=data,
    excludes=excludes,
    hiddenimports=hiddenimports,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="ndrive",
    console=False,
    debug=False,
    strip=False,
    upx=False,
    icon=icon,
    version=properties_rc,
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="ndrive")

info_plist = {
    "CFBundleName": "NuxeoDrive",
    "CFBundleShortVersionString": version,
    "CFBundleURLTypes": {
        "CFBundleURLName": "org.nuxeo.nxdrive.direct-edit",
        "CFBundleTypeRole": "Editor",
        "CFBundleURLSchemes": ["nxdrive"],
    },
    "LSUIElement": True,  # Implies LSBackgroundOnly, no icon in the Dock
}

app = BUNDLE(
    coll,
    name="Nuxeo Drive.app",
    icon=icon,
    info_plist=info_plist,
    bundle_identifier="org.nuxeo.drive",
)
