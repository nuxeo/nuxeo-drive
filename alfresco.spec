# -*- mode: python -*-
import io
import os
import os.path
from pathlib import Path
import re
import sys


def get_version(init_file):
    """Find the current version."""

    with io.open(init_file, encoding="utf-8") as handler:
        for line in handler.readlines():
            if line.startswith("__alfresco_version__"):
                return re.findall(r"\"(.+)\"", line)[0]

def update_supported_server_list(file_path):
    with open(file_path, "w") as f:
        f.write("# One server key per line.\n# These keys must match registered ServerTypeConfig.key values.\nALFRESCO")


cwd = os.getcwd()
tools = os.path.join(cwd, "tools")
nxdrive = os.path.join(cwd, "nxdrive")
data = os.path.join(nxdrive, "drive", "data")
alfresco_qml = os.path.join(nxdrive, "alfresco", "gui", "qml")
nuxeo_qml = os.path.join(nxdrive, "nuxeo", "gui", "qml")
supported_server_list = os.path.join(nxdrive, "supported_server_list.txt")

update_supported_server_list(supported_server_list)

icon = {
    "darwin": os.path.join(tools, "osx", "app_icon.icns"),
    "linux": os.path.join(tools, "linux", "app_icon.png"),
    "win32": os.path.join(tools, "windows", "app_icon.ico"),
}[sys.platform]

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

data = [
    (data, "data"),
    (data, "nxdrive/drive/data"),
    (supported_server_list, "nxdrive"),
    (supported_server_list, "data/server_list"),
    (alfresco_qml, "nxdrive/alfresco/gui/qml"),
    (nuxeo_qml, "nxdrive/nuxeo/gui/qml"),
]
migrations = Path(nxdrive, "drive", "dao", "migrations")
hiddenimports = [
    migration.relative_to(cwd).with_suffix("").as_posix().replace("/", ".")
    for migration in migrations.glob("**/[0-9]*.py")
]

# Classes loaded dynamically via importlib.import_module() or auto-discovery
# in __init__.py / server_type.load_class(), so PyInstaller cannot trace them.
hiddenimports += [
    # Registration modules (auto-discovered at startup)
    "nxdrive.nuxeo.registration",
    "nxdrive.alfresco.registration",
    # Nuxeo dynamic classes
    "nxdrive.nuxeo.engine.engine",
    "nxdrive.nuxeo.direct_edit",
    "nxdrive.nuxeo.direct_download",
    "nxdrive.nuxeo.client.workflow",
    "nxdrive.nuxeo.auth.oauth2",
    "nxdrive.nuxeo.gui.folders_model",
    "nxdrive.nuxeo.gui.auth_callback_store",
    "nxdrive.nuxeo.protocol",
    # Alfresco dynamic classes
    "nxdrive.alfresco.engine.engine",
    "nxdrive.alfresco.auth.oauth2",
    "nxdrive.alfresco.engine.processor",
    "nxdrive.alfresco.client.remote",
    "nxdrive.alfresco.engine.watcher.remote_watcher",
    "alfresco",
    "alfresco._utils",
    "alfresco.client",
    "alfresco.auth",
    "alfresco.exceptions",
    "alfresco.api",
    "alfresco.api.base",
    "alfresco.api.nodes",
    "alfresco.api.people",
    "alfresco.api.search",
    "alfresco.api.sites",
    "alfresco.api.sync_service",
    "alfresco.models",
    "alfresco.models.node",
    "alfresco.models.person",
    "alfresco.models.site",
    "alfresco.models.search",
]

version = get_version(os.path.join(nxdrive, "__init__.py"))
properties_rc = None

if sys.platform == "win32":
    # Set executable properties
    properties_tpl = tools + "\\windows\\properties_tpl.rc"
    properties_rc = tools + "\\windows\\properties.rc"
    if os.path.isfile(properties_rc):
        os.remove(properties_rc)

    version_tuple = tuple(map(int, version.split(".") + [0] * (3 - version.count("."))))

    with open(properties_tpl, encoding="utf-8") as tpl, open(
        properties_rc, "w", encoding="utf-8"
    ) as out:
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
    name="alfresco-drive",
    console=False,
    debug=False,
    strip=False,
    upx=False,
    icon=icon,
    version=properties_rc,
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="alfresco-drive")

info_plist = {
    "CFBundleName": "AlfrescoDrive",
    "CFBundleShortVersionString": version,
    # CFBundleURLTypes MUST be an array of dicts per Apple's spec
    # (https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleurltypes).
    # If declared as a single dict, macOS LaunchServices silently fails to
    # deliver nxdrive:// URLs as QFileOpenEvent to the running app.
    "CFBundleURLTypes": [
        {
            "CFBundleURLName": "org.alfresco.nxdrive.direct-edit",
            "CFBundleTypeRole": "Editor",
            "CFBundleURLSchemes": ["nxdrive"],
        },
    ],
    "LSUIElement": True,  # Implies LSBackgroundOnly, no icon in the Dock
}

app = BUNDLE(
    coll,
    name="Alfresco Drive.app",
    icon=icon,
    info_plist=info_plist,
    bundle_identifier="org.alfresco.drive",
)
