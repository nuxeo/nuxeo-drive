"""
versions.yml management.
Requires the pyyaml module.
"""

import argparse
import glob
import hashlib
import os
import os.path
from datetime import datetime, timezone

import yaml

__version__ = "1.1.0"
__all__ = ("create", "delete", "merge", "promote")


def _load():
    """Get initial versions."""

    with open("versions.yml") as yml:
        return yaml.safe_load(yml.read()) or {}


def _dump(versions):
    """Write back the updated versions details."""

    with open("versions.yml", "w") as yml:
        yaml.safe_dump(versions or "", yml, indent=4, default_flow_style=False)


def wrap(func):
    """Decorator to ease versions.yml management."""

    def func_wrapper(*args, **kwargs):
        """
        Call the original function on the loaded versions.yml content.
        `versions` is a dict, so `func` can change its content. This is a feature here.
        """
        versions = _load()
        func(versions, *args, **kwargs)
        _dump(versions)

    return func_wrapper


@wrap
def check(versions):
    """Check versions file integrity.."""

    assert isinstance(versions, dict) and versions, versions


def create(version, category):
    # type: (str, str) -> None
    """Create a version file with default values."""

    # Compute installers checksum
    checksum_appimage = checksum_dmg = checksum_exe = checksum_exe_admin = None
    folder = os.getenv("ARTIFACTS_FOLDER", "dist/")
    paths = (
        "{}nuxeo-drive-{}-x86_64.AppImage",
        "{}nuxeo-drive-{}.dmg",
        "{}nuxeo-drive-{}.exe",
        "{}nuxeo-drive-{}-admin.exe",
    )
    for path in paths:
        path = path.format(folder, version)
        if not os.path.isfile(path):
            continue

        with open(path, "rb") as installer:
            checksum = hashlib.sha256(installer.read()).hexdigest()
            if path.endswith("AppImage"):
                checksum_appimage = checksum
            elif path.endswith("dmg"):
                checksum_dmg = checksum
            elif "admin" in path:
                checksum_exe_admin = checksum
            else:
                checksum_exe = checksum

    # Create the version file
    output = "{}.yml".format(version)

    """
    We set 10.3-SNAPSHOT to allow presales to test the current dev version.
    Same for the future 10.10 to not block updates when it will be available.
    Note that we removed the following section with NXDRIVE-1419:

    min_all:
        "7.10": "7.10-HF47"
        "8.10": "8.10-HF38"
        "9.10": "9.10-HF20"
        "10.3": "10.3-SNAPSHOT"
        "10.10": "10.10-SNAPSHOT"
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yml = {
        version: {
            "checksum": {"algo": "sha256"},
            "date": today,
            "min": "7.10",
            "type": category,
        }
    }
    if checksum_appimage:
        yml[version]["checksum"]["appimage"] = checksum_appimage
    if checksum_dmg:
        yml[version]["checksum"]["dmg"] = checksum_dmg
    if checksum_exe:
        yml[version]["checksum"]["exe"] = checksum_exe
    if checksum_exe_admin:
        yml[version]["checksum"]["exe-admin"] = checksum_exe_admin
    with open(output, "w") as versions:
        versions.write(yaml.dump(yml))


@wrap
def delete(versions, version):
    """Delete a given version."""

    versions.pop(version, None)
    try:
        os.remove("{}.yml".format(version))
    except OSError:
        pass


@wrap
def merge(versions):
    """Merge any single version file into versions.yml."""

    for filename in glob.glob("*.yml"):
        if filename == "versions.yml":
            continue

        version = filename[:-4]
        with open(filename) as yml:
            info = yaml.safe_load(yml.read())
            versions[version] = info[version]


@wrap
def promote(versions, version, category):
    """Promote a given version to the given category."""

    versions[version]["type"] = category


def main():
    """Main logic."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--add", help="add a new version")
    parser.add_argument(
        "--check", action="store_true", help="check the versions file integrity"
    )
    parser.add_argument("--delete", help="delete a version")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="merge any single version file into versions.yml",
    )
    parser.add_argument("--promote", help="change a given version to the next category")
    parser.add_argument(
        "--type",
        choices=("alpha", "beta", "release"),
        help="version type (mandatory for --create and --promote)",
    )
    args = parser.parse_args()

    if args.add:
        assert args.type, "You must provide the version type"
        return create(args.add, args.type)
    elif args.check:
        return check()
    elif args.delete:
        return delete(args.delete)
    elif args.merge:
        return merge()
    elif args.promote:
        assert args.type, "You must provide the version type"
        return promote(args.promote, args.type)

    return 1


if __name__ == "__main__":
    exit(main())
