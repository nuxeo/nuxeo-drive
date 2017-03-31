#!/bin/sh -eu
#
# Deploy a release: it means moving artifacts from the staging site to the production's one, uploading to PyPi and
# converting GitHub pre-release to release.
#
# Warning: do not execute this script manually but from Jenkins.
#

release() {
    local latest_release
    local drive_version
    local release_url
    local path
    local dmg
    local msi

    latest_release="$(git tag -l "release-*" --sort=-taggerdate | head -n1)"
    drive_version="$(echo "${latest_release}" | cut -d'-' -f2)"

    if [ "${drive_version}" = '' ]; then
        echo ">>> No Drive version found."
        exit 1
    fi

    path="/var/www/community.nuxeo.com/static"
    dmg="${path}/drive/nuxeo-drive-${drive_version}-osx.dmg"
    msi="${path}/drive/nuxeo-drive-${drive_version}-win32.msi"

    echo ">>> [release ${drive_version}] Deploying to the production website"
    ssh -T nuxeo@lethe.nuxeo.com <<EOF
# Copy artifacts from staging website to the production one
cp -vf ${path}/drive-tests/*${drive_version}* ${path}/drive

# Create symbolic links of the latest packages
ln -sfv ${dmg} ${path}/drive/latest/nuxeo-drive.dmg
ln -sfv ${msi} ${path}/drive/latest/nuxeo-drive.msi

# Create symbolic links of the latest packages for all supported versions of Nuxeo
for nuxeo_version in 6.0 7.10 8.10 9.1-SNAPSHOT; do
    mkdir -pv ${path}/drive/latest/\$nuxeo_version
    ln -sfv ${dmg} ${path}/drive/latest/\$nuxeo_version/nuxeo-drive.dmg
    ln -sfv ${msi} ${path}/drive/latest/\$nuxeo_version/nuxeo-drive.msi
done
EOF

    echo ">>> [release ${drive_version}] Uploading to PyPi"
    python setup.py sdist upload

    echo ">>> [release ${drive_version}] Saving release on GitHub"
    # Fetch the pre-release informations to find the complete URL
    # Note: if the pre-release is still a draft, the command below will fail
    curl --silent -X GET -n -o prerelease.json \
        "https://api.github.com/repos/nuxeo/nuxeo-drive/releases/tags/${latest_release}"

    release_url="$(grep '"url"' prerelease.json | head -1 | cut -d'"' -f4)"
    echo "Pre-release URL: ${release_url}"
    curl -X PATCH -i -n -d '{ "prerelease": false }' "${release_url}"
}

release
