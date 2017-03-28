#!/bin/sh -eu
#
# Deploy a release: it means moving artifacts from the staging site to the production's one, uploading to PyPi and
# converting GitHub pre-release to release.
#
# Warning: do not execute this script manually but from Jenkins.
#

export RELEASE_TYPE="${RELEASE_TYPE:=nightly}"

release() {
    local latest_release=$(git tag -l "release-*" --sort=-taggerdate | head -n1)
    local drive_version=$(echo ${latest_release} | cut -d'-' -f2)

    if [ "${drive_version}" = '' ]; then
        echo ">>> No Drive version found."
        exit 1
    fi

    echo ">>> [release ${drive_version}] Deploying to the production website"
    ssh nuxeo@lethe.nuxeo.com "cp -vf /var/www/community.nuxeo.com/static/drive-tests/*${drive_version}* /var/www/community.nuxeo.com/static/drive/"

    echo ">>> [release ${drive_version}] Uploading to PyPi"
    python setup.py sdist upload

    echo ">>> [release ${drive_version}] Saving release on GitHub"
    # Fetch the pre-release informations to find the complete URL
    # Note: if the pre-release is still a draft, the command below will fail
    curl --silent -X GET -n -o prerelease.json \
        https://api.github.com/repos/nuxeo/nuxeo-drive/releases/tags/${latest_release}

    local release_url=$(grep '"url"' prerelease.json | head -1 | cut -d'"' -f4)
    echo "Pre-release URL: ${release_url}"
    curl -X PATCH -i -n -d '{ "prerelease": false }' ${release_url}
}

main() {
    echo ">>> Release type: ${RELEASE_TYPE}"

    if [ "${RELEASE_TYPE}" != "release" ]; then
        echo "Bad RELEASE_TYPE."
        exit 1
    fi

    release
}

main
