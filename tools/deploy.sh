#!/bin/sh -eu
#
# Deploy a release: it means moving artifacts from the staging site to the production's one and
# converting GitHub pre-release to release.
#
# Warning: do not execute this script manually but from Jenkins.
#

release() {
    # Take the beta version to release as 1st argument.
    local latest_release
    local drive_version
    local release_url
    local path
    local dmg
    local exe

    drive_version="$1"
    latest_release="release-${drive_version}"

    if [ "${drive_version}" = 'x.y.z' ]; then
        echo ">>> No Drive version found."
        exit 1
    fi

    path="/var/www/community.nuxeo.com/static/drive-updates"
    dmg="${path}/beta/nuxeo-drive-${drive_version}.dmg"
    exe="${path}/beta/nuxeo-drive-${drive_version}.exe"

    echo ">>> [${latest_release}] Deploying to the production website"
    ssh -T nuxeo@lethe.nuxeo.com <<EOF
# Move beta files into the release folder
mv -vf ${path}/beta/*${drive_version}* ${path}/release

# Create symbolic links of the latest packages
ln -sfv ${dmg} ${path}/nuxeo-drive.dmg
ln -sfv ${exe} ${path}/nuxeo-drive.exe
EOF

    echo ">>> [release ${drive_version}] Generating the versions file"
    python -m pip install --user --upgrade pyaml
    rsync -vz nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-updates/versions.yml .
    python tools/versions.py --promote "${drive_version}"
    rsync -vz versions.yml nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-updates/

    echo ">>> [${latest_release}] Saving release on GitHub"
    # Fetch the pre-release informations to find the complete URL
    # Note: if the pre-release is still a draft, the command below will fail
    curl --silent -X GET -n -o prerelease.json \
        "https://api.github.com/repos/nuxeo/nuxeo-drive/releases/tags/${latest_release}"

    release_url="$(grep '"url"' prerelease.json | head -1 | cut -d'"' -f4)"
    echo "Pre-release URL: ${release_url}"
    curl -X PATCH -i -n -d '{ "prerelease": false }' "${release_url}"
}

release "$@"
