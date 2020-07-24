#!/bin/bash -eu
#
# Deploy a release: it means moving artifacts from the staging site to the production's one and
# converting GitHub pre-release to release.
#
# Warning: do not execute this script manually but from Jenkins.
#

. "tools/env.sh"

release() {
    # Take the beta version to release as 1st argument.
    local latest_release
    local drive_version

    drive_version="$1"
    latest_release="release-${drive_version}"

    if [ "${drive_version}" = 'x.y.z' ]; then
        echo ">>> No Drive version found."
        exit 1
    fi

    echo ">>> [${latest_release}] Deploying to the production website"
    ssh -o "StrictHostKeyChecking=no" -T nuxeo@lethe.nuxeo.com <<EOF
# Move beta files into the release folder
mv -vf ${REMOTE_PATH_PROD}/beta/*${drive_version}* ${REMOTE_PATH_PROD}/release/

# Create symbolic links of the latest packages
ln -sfv "${REMOTE_PATH_PROD}/release/nuxeo-drive-${drive_version}-x86_64.AppImage" ${REMOTE_PATH_PROD}/nuxeo-drive-x86_64.AppImage
ln -sfv "${REMOTE_PATH_PROD}/release/nuxeo-drive-${drive_version}.dmg" ${REMOTE_PATH_PROD}/nuxeo-drive.dmg
ln -sfv "${REMOTE_PATH_PROD}/release/nuxeo-drive-${drive_version}.exe" ${REMOTE_PATH_PROD}/nuxeo-drive.exe
EOF

    echo ">>> [release ${drive_version}] Generating the versions file"
    python3 -m pip install --user -U setuptools wheel
    python3 -m pip install --user pyyaml==5.3.1
    rsync -e "ssh -o StrictHostKeyChecking=no" -vz nuxeo@lethe.nuxeo.com:"${REMOTE_PATH_PROD}/versions.yml" .
    python3 tools/versions.py --promote "${drive_version}" --type "release"
    rsync -e "ssh -o StrictHostKeyChecking=no" -vz versions.yml nuxeo@lethe.nuxeo.com:"${REMOTE_PATH_PROD}/"
}

release "$@"
