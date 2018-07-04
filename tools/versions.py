# coding: utf-8
"""
versions.yml generator.
Requires the pyaml module.
"""

from __future__ import print_function, unicode_literals

import argparse
import glob
import hashlib

__version__ = "0.0.1"


def create(version):
    # type: (str) -> None
    """ Create a version file with default values. """

    category = "beta"
    if "-" in version:
        category, version = version.split("-")

    # Compute installers checksum
    checksum_dmg = checksum_exe = None
    paths = ("dist/nuxeo-drive-{}.dmg", "dist/nuxeo-drive-{}.exe")
    for path in paths:
        with open(path.format(version), "rb") as installer:
            checksum = hashlib.sha256(installer.read()).hexdigest()
            if path.endswith("dmg"):
                checksum_dmg = checksum
            else:
                checksum_exe = checksum

    # Create the version file
    output = "{}.yml".format(version)
    yml = """{}:
    min: '7.10'
    type: {}
    checksum:
        algo: sha256
        dmg: {}
        exe: {}
""".format(
        version, category, checksum_dmg, checksum_exe
    )
    with open(output, "w") as versions:
        versions.write(yml)


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
    parser.add_argument(
        "--merge",
        action="store_true",
        help="merge any single version file into versions.yml",
    )
    parser.add_argument("--promote", help="change a given version to the next category")
    args = parser.parse_args()

    if args.merge:
        return merge()
    elif args.promote:
        return promote(args.promote)
    elif args.add:
        return create(args.add)

    return 1


if __name__ == "__main__":
    exit(main())
