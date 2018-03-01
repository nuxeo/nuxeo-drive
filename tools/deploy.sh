#!/bin/sh -eu
#
# Deploy a release: it means moving artifacts from the staging site to the production's one, uploading to PyPi and
# converting GitHub pre-release to release.
#
# Warning: do not execute this script manually but from Jenkins.
#

release() {
    # Takes the beta version to release as 1st argument.
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

    path="/var/www/community.nuxeo.com/static"
    dmg="${path}/drive/nuxeo-drive-${drive_version}-osx.dmg"
    exe="${path}/drive/nuxeo-drive-${drive_version}-win32.exe"

    echo ">>> [${latest_release}] Deploying to the production website"
    ssh -T nuxeo@lethe.nuxeo.com <<EOF
# Copy artifacts from staging website to the production one
cp -vf ${path}/drive-tests/*${drive_version}* ${path}/drive

# Create symbolic links of the latest packages
ln -sfrv ${dmg} ${path}/drive/latest/nuxeo-drive.dmg
ln -sfrv ${exe} ${path}/drive/latest/nuxeo-drive.exe

# Create symbolic links of the latest packages for all supported versions of Nuxeo
for folder in \$(find ${path}/drive/latest -maxdepth 1 -type d); do
    ln -sfrv ${dmg} \$folder/nuxeo-drive.dmg
    ln -sfrv ${exe} \$folder/nuxeo-drive.exe
done
EOF

    # TODO: To remove?
    # echo ">>> [${latest_release}] Uploading to PyPi"
    # python setup.py sdist upload

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
