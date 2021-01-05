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
    "PyQt*/Qt/lib/QtBluetooth*",
    "PyQt*/Qt/lib/QtConcurrent*",
    "PyQt*/Qt/lib/QtLocation*",
    "PyQt*/Qt/lib/QtMultimedia*",
    "PyQt*/Qt/lib/QtNfc*",
    "PyQt*/Qt/lib/QtPositioning*",
    "PyQt*/Qt/lib/QtQuickTest*",
    "PyQt*/Qt/lib/QtSensors*",
    "PyQt*/Qt/lib/QtSql*",
    "PyQt*/Qt/lib/QtTest*",
    "PyQt*/Qt/lib/QtWeb*",
    "PyQt*/Qt/lib/QtXml*",
    "PyQt*/Qt/plugins/bearer",
    "PyQt*/Qt/plugins/imageformats/*q[a-rt-z]*",  # Keep qs* for qsvg
    "PyQt*/Qt/plugins/mediaservice",
    "PyQt*/Qt/plugins/position",
    "PyQt*/Qt/plugins/printsupport",
    "PyQt*/Qt/plugins/sensorgestures",
    "PyQt*/Qt/plugins/sensors",
    "PyQt*/Qt/plugins/sqldrivers",
    "PyQt*/Qt/qml/Qt/labs/calendar",
    "PyQt*/Qt/qml/Qt/labs/location",
    "PyQt*/Qt/qml/Qt/labs/sharedimage",
    "PyQt*/Qt/qml/Qt/labs/wavefrontmesh",
    "PyQt*/Qt/qml/Qt/test",
    "PyQt*/Qt/qml/Qt/Web*",
    "PyQt*/Qt/qml/QtAudioEngine",
    "PyQt*/Qt/qml/QtBluetooth",
    "PyQt*/Qt/qml/QtCanvas3D",
    "PyQt*/Qt/qml/QtGraphicalEffects",
    "PyQt*/Qt/qml/QtLocation",
    "PyQt*/Qt/qml/QtMultimedia",
    "PyQt*/Qt/qml/QtNfc",
    "PyQt*/Qt/qml/QtPositioning",
    "PyQt*/Qt/qml/QtQml/RemoteObjects",
    "PyQt*/Qt/qml/QtQml/StateMachine",
    "PyQt*/Qt/qml/QtQuick3D",
    "PyQt*/Qt/qml/QtQuick/Controls.2/designer",
    "PyQt*/Qt/qml/QtQuick/Extras/designer",
    "PyQt*/Qt/qml/QtQuick/Particles.2",
    "PyQt*/Qt/qml/QtQuick/Scene*",
    "PyQt*/Qt/qml/QtRemoteObjects",
    "PyQt*/Qt/qml/QtSensors",
    "PyQt*/Qt/qml/QtTest",
    "PyQt*/Qt/qml/QtWeb*",
    "PyQt*/QtPositioning.*",
    "PyQt*/QtPrintSupport.*",
    "PyQt*/QtSensors.*",
    "PyQt*/QtSerialPort.*",
    "PyQt*/QtTest.*",
    "PyQt*/Qt/translations",
    "PyQt*/QtBluetooth.*",
    # "PyQt*/QtDBus.*",
    "PyQt*/QtDesigner.*",
    "PyQt*/QtHelp.*",
    "PyQt*/QtLocation.*",
    "PyQt*/QtMacExtras.*",
    "PyQt*/QtMultimedia*.*",
    "PyQt*/QtNfc.*",
    "PyQt*/QtSql.*",
    "PyQt*/QtWeb*",
    "PyQt*/QtXml*",
    "PyQt*/translations",
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
    # Botocore has a lot of useless files (only S3 and endpoints.json are interesting)
    "botocore/data/[0-9a-df-rt-z]*",
    "botocore/data/e[a-mo-z]*",  # Keep en*
    "botocore/data/en[a-c-e-z]*",  # Keep only end*
    "botocore/data/s[0-24-9a-z]*",  # Keep s3*
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
