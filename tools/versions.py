# coding: utf-8
"""
versions.yml management.
Requires the pyaml module.
"""

from __future__ import print_function, unicode_literals

import argparse
import glob
import hashlib
import os
import os.path

__version__ = "0.0.4"


def create(version):
    # type: (str) -> None
    """ Create a version file with default values. """

    category = "beta"
    if "-" in version:
        category, version = version.split("-")

    # Compute installers checksum
    checksum_dmg = checksum_exe = checksum_exe_admin = None
    paths = (
        "dist/nuxeo-drive-{}.dmg",
        "dist/nuxeo-drive-{}.exe",
        "dist/nuxeo-drive-{}-admin.exe",
    )
    for path in paths:
        if os.getenv("TESTING") and not os.path.isfile(path.format(version)):
            continue

        with open(
            path.format(version), "rb"  # Set TESTING=1 envar to skip the error
        ) as installer:
            checksum = hashlib.sha256(installer.read()).hexdigest()
            if path.endswith("dmg"):
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
    yml = """{}:
    min: "7.10"
    type: {}
    checksum:
        algo: sha256
        dmg: {}
        exe: {}
        exe-admin: {}
""".format(
        version, category, checksum_dmg, checksum_exe, checksum_exe_admin
    )
    with open(output, "w") as versions:
        versions.write(yml)


def delete(version):
    """ Delete a given version. """

    import yaml

    # Get initial versions
    with open("versions.yml") as yml:
        versions = yaml.safe_load(yml.read())

    # Remove the version everywhere
    versions.pop(version, None)
    try:
        os.remove("{}.yml".format(version))
    except OSError:
        pass

    # Write back the updated versions details
    with open("versions.yml", "w") as yml:
        yaml.safe_dump(versions, yml, indent=4, default_flow_style=False)


def merge():
    """ Merge any single version file into versions.yml. """

    import yaml

    # Get initial versions
    with open("versions.yml") as yml:
        versions = yaml.safe_load(yml.read())

    # Find new versions and merge them together
    for filename in glob.glob("*.yml"):
        if filename == "versions.yml":
            continue

        version = filename[:-4]
        with open(filename) as yml:
            info = yaml.safe_load(yml.read())
            versions[version] = info[version]

    # Write back the updated versions details
    with open("versions.yml", "w") as yml:
        yaml.safe_dump(versions, yml, indent=4, default_flow_style=False)


def promote(version):
    """ Promote a given version to the next category. """

    import yaml

    # Get initial versions
    with open("versions.yml") as yml:
        versions = yaml.safe_load(yml.read())

    categories = {
        # current -> new
        "beta": "release",
        "release": "release",
        "archive": "archive",
    }
    versions[version]["type"] = categories[versions[version]["type"]]

    # Write back the updated versions details
    with open("versions.yml", "w") as yml:
        yaml.safe_dump(versions, yml, indent=4, default_flow_style=False)


def main():
    """ Main logic. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--add", help="add a new version")
    parser.add_argument("--delete", help="delete a version")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="merge any single version file into versions.yml",
    )
    parser.add_argument("--promote", help="change a given version to the next category")
    args = parser.parse_args()

    if args.add:
        return create(args.add)
    elif args.delete:
        return delete(args.delete)
    elif args.merge:
        return merge()
    elif args.promote:
        return promote(args.promote)

    return 1


if __name__ == "__main__":
    exit(main())
