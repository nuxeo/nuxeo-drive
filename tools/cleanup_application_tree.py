"""
Remove files from the package that are not needed and too big.
This script can be launched after PyInstaller and before installers creation.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Generator, List, Tuple

FILES: Tuple[str] = (
    "PySide6*/Qt/lib/QtBluetooth*",
    "PySide6*/Qt/lib/QtConcurrent*",
    "PySide6*/Qt/lib/QtLocation*",
    "PySide6*/Qt/lib/QtMultimedia*",
    "PySide6*/Qt/lib/QtNfc*",
    "PySide6*/Qt/lib/QtPositioning*",
    "PySide6*/Qt/lib/QtQuickTest*",
    "PySide6*/Qt/lib/QtSensors*",
    "PySide6*/Qt/lib/QtSql*",
    "PySide6*/Qt/lib/QtTest*",
    "PySide6*/Qt/lib/QtWeb*",
    "PySide6*/Qt/lib/QtXml*",
    "PySide6*/Qt/plugins/bearer",
    "PySide6*/Qt/plugins/imageformats/*q[a-rt-z]*",  # Keep qs* for qsvg
    "PySide6*/Qt/plugins/mediaservice",
    "PySide6*/Qt/plugins/position",
    "PySide6*/Qt/plugins/printsupport",
    "PySide6*/Qt/plugins/sensorgestures",
    "PySide6*/Qt/plugins/sensors",
    "PySide6*/Qt/plugins/sqldrivers",
    "PySide6*/Qt/qml/Qt/labs/calendar",
    "PySide6*/Qt/qml/Qt/labs/location",
    "PySide6*/Qt/qml/Qt/labs/sharedimage",
    "PySide6*/Qt/qml/Qt/labs/wavefrontmesh",
    "PySide6*/Qt/qml/Qt/test",
    "PySide6*/Qt/qml/Qt/Web*",
    "PySide6*/Qt/qml/QtAudioEngine",
    "PySide6*/Qt/qml/QtBluetooth",
    "PySide6*/Qt/qml/QtCanvas3D",
    "PySide6*/Qt/qml/QtGraphicalEffects",
    "PySide6*/Qt/qml/QtLocation",
    "PySide6*/Qt/qml/QtMultimedia",
    "PySide6*/Qt/qml/QtNfc",
    "PySide6*/Qt/qml/QtPositioning",
    "PySide6*/Qt/qml/QtQml/RemoteObjects",
    "PySide6*/Qt/qml/QtQml/StateMachine",
    "PySide6*/Qt/qml/QtQuick3D",
    "PySide6*/Qt/qml/QtQuick/Controls.2/designer",
    "PySide6*/Qt/qml/QtQuick/Extras/designer",
    "PySide6*/Qt/qml/QtQuick/Particles.2",
    "PySide6*/Qt/qml/QtQuick/Scene*",
    "PySide6*/Qt/qml/QtRemoteObjects",
    "PySide6*/Qt/qml/QtSensors",
    "PySide6*/Qt/qml/QtTest",
    "PySide6*/Qt/qml/QtWeb*",
    "PySide6*/QtPositioning.*",
    "PySide6*/QtPrintSupport.*",
    "PySide6*/QtSensors.*",
    "PySide6*/QtSerialPort.*",
    "PySide6*/QtTest.*",
    "PySide6*/Qt/translations",
    "PySide6*/QtBluetooth.*",
    # "PySide6*/QtDBus.*",
    "PySide6*/QtDesigner.*",
    "PySide6*/QtHelp.*",
    "PySide6*/QtLocation.*",
    "PySide6*/QtMacExtras.*",
    "PySide6*/QtMultimedia*.*",
    "PySide6*/QtNfc.*",
    "PySide6*/QtSql.*",
    "PySide6*/QtWeb*",
    "PySide6*/QtXml*",
    "PySide6*/translations",
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
    "*Qt*Quick3D*",
    "*Qt*QuickTest*",
    "*Qt*RemoteObjects*",
    "*Qt*Sensors*",
    "*Qt*SerialPort*",
    "*Qt*Sql*",
    "*Qt*Test*",
    "*Qt*Web*",
    "*Qt*WinExtras*",
    "*Qt*Xml*",
    # Boto3 has useless files (only S3 is interesting)
    "boto3/data/[0-9a-rt-z]*",
    "boto3/data/s[0-24-9a-z]*",  # Keep s3*
    "boto3/examples",
    # Botocore has a lot of useless files
    # (only S3, endpoints.json, sdk-default-configuration.json and partitions.json are required)
    "botocore/data/[0-9a-df-oq-rt-z]*",
    "botocore/data/e[a-mo-z]*",  # Keep en*
    "botocore/data/en[a-c-e-z]*",  # Keep only end*
    "botocore/data/s[0-24-9a-ce-z]*",  # Keep s3*
    "botocore/data/sd[a-jl-z]*",
    "botocore/data/p[b-z]*",
    "botocore/data/pa[a-qs-z]*",
)


def find_useless_files(folder: Path) -> Generator[Path, None, None]:
    """Recursively yields files we want to remove."""
    for pattern in FILES:
        yield from folder.glob(pattern)


def main(args: List[str]) -> int:
    """
    Purge unneeded files from the packaged application.
    Take one or more folder arguments: "ndrive", "Nuxeo Drive.app".
    """
    for folder in args:
        print(f">>> [{folder}] Purging unneeded files")
        for file in find_useless_files(Path(folder)):
            if file.is_dir():
                shutil.rmtree(file)
            else:
                os.remove(file)
            print(f"[X] Removed {file}")
        print(f">>> [{folder}] Folder purged.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
