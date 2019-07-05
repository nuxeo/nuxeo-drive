# coding: utf-8
"""
Remove files from the package that are not needed and too big.
This script can be launched after PyInstaller and before the DMG or EXE creation.
"""
import os
import shutil
import sys
from pathlib import Path
from typing import Generator, List, Set


FILES: Set[str] = {
    "PyQt*/Qt/lib",  # Contains only WebEngineCore.framework on macOS
    "PyQt*/Qt/plugins/mediaservice",
    "PyQt*/Qt/plugins/position",
    "PyQt*/Qt/plugins/printsupport",
    "PyQt*/Qt/plugins/sensorgestures",
    "PyQt*/Qt/plugins/sensors",
    "PyQt*/Qt/plugins/sqldrivers",
    "PyQt*/Qt/qml/Qt/labs/location",
    "PyQt*/Qt/qml/Qt/WebSockets",
    "PyQt*/Qt/qml/QtAudioEngine",
    "PyQt*/Qt/qml/QtBluetooth",
    "PyQt*/Qt/qml/QtCanvas3D",
    "PyQt*/Qt/qml/QtGraphicalEffects",
    "PyQt*/Qt/qml/QtLocation",
    "PyQt*/Qt/qml/QtMultimedia",
    "PyQt*/Qt/qml/QtNfc",
    "PyQt*/Qt/qml/QtPositioning",
    "PyQt*/Qt/qml/QtQuick/Controls.2/designer",
    "PyQt*/Qt/qml/QtQuick/Extras/designer",
    "PyQt*/Qt/qml/QtQuick/Particles.2",
    "PyQt*/Qt/qml/QtQuick/Scene2D",
    "PyQt*/Qt/qml/QtQuick/Scene3D",
    "PyQt*/Qt/qml/QtSensors",
    "PyQt*/Qt/qml/QtTest",
    "PyQt*/Qt/qml/QtWebChannel",
    "PyQt*/Qt/qml/QtWebEngine",
    "PyQt*/Qt/qml/QtWebSockets",
    "PyQt*/QtPositioning.*",
    "PyQt*/QtPrintSupport.*",
    "PyQt*/QtSensors.*",
    "PyQt*/QtSerialPort.*",
    "PyQt*/QtTest.*",
    "PyQt*/Qt/translations/qtdeclarative*",
    "PyQt*/Qt/translations/qt_help*",
    "PyQt*/Qt/translations/qtmultimedia*",
    "PyQt*/Qt/translations/qtserialport*",
    "PyQt*/QtBluetooth.*",
    # "PyQt*/QtDBus.*",
    "PyQt*/QtDesigner.*",
    "PyQt*/QtHelp.*",
    "PyQt*/QtLocation.*",
    "PyQt*/QtMacExtras.*",
    "PyQt*/QtMultimedia*.*",
    "PyQt*/QtNfc.*",
    "PyQt*/QtSql.*",
    "PyQt*/QtWebChannel.*",
    "PyQt*/QtWebEngine*.*",
    "PyQt*/QtWebSockets.*",
    "PyQt*/QtXmlPatterns.*",
    "PyQt*/QtXml.*",
    "*Qt*Bluetooth*",
    "*Qt*Concurrent*",
    # "*Qt*DBus*",
    "*Qt*Designer*",
    "*Qt*Help*",
    "*Qt*Location*",
    "*Qt*MacExtras*",
    "*Qt*Multimedia*",
    "*Qt*Nfc*",
    "*Qt*Positioning*",
    "*Qt*QuickParticles*",
    "*Qt*QuickTest*",
    "*Qt*Sensors*",
    "*Qt*SerialPort*",
    "*Qt*Sql*",
    "*Qt*Test*",
    "*Qt*WebChannel*",
    "*Qt*WebEngine*",
    "*Qt*WebSockets*",
    "*Qt*WinExtras*",
    "*Qt*Xml*",
    "*Qt*XmlPatterns*",
}


def find_useless_files(folder: Path) -> Generator[Path, None, None]:
    """Recursively yields files we want to remove."""
    for pattern in FILES:
        for path in folder.glob(pattern):
            yield path


def main(args: List[str]) -> int:
    """
    Purge uneeded files from the packaged application.
    Take one or more folder arguments: "ndrive", "Nuxeo Drive.app".
    """
    for folder in args:
        print(f">>> [{folder}] Purging uneeded files")
        for file in find_useless_files(Path(folder)):
            if file.is_dir():
                shutil.rmtree(file)
            else:
                os.remove(file)
            print(f"[X] Removed {file}")
        print(f">>> [{folder}] Folder purged.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
