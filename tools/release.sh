#!/bin/sh -eu
#
# Create a new release: it means creating a new beta, managing GitHub actions and
# deploying artifacts to the staging site.
#
# Warning: do not execute this script manually but from Jenkins.
#

changelog() {
    # Create the draft.json file with the pre-release content
    local drive_version
    local changelog
    local complete_changelog

    drive_version="$1"
    changelog="$(python tools/changelog.py --format=md)"
    complete_changelog="$(cat <<EOF
${changelog}

If you have a Nuxeo Drive instance running against a LTS or a Fast Track version of Nuxeo, a notification about this new version should be displayed in the systray menu within an hour allowing you to upgrade (can bypass this delay by restarting Drive).

It is also directly available for download from:
- http://community.nuxeo.com/static/drive-tests/nuxeo-drive-${drive_version}-win32.msi
- http://community.nuxeo.com/static/drive-tests/nuxeo-drive-${drive_version}-osx.dmg

Or from the Nuxeo Drive tab in the User Center of a LTS or a Fast Track version of Nuxeo.
EOF
)"

    # Escape lines feed and double quotes for JSON
    complete_changelog="$(echo "${complete_changelog}" | sed 's|$|\\n|g ; s|\"|\\\"|g')"

    # Create the pre-release draft
    [ -f draft.json ] && rm -f draft.json
    cat > draft.json <<EOF
{
    "tag_name": "release-${drive_version}",
    "target_commitish": "master",
    "name": "${drive_version}",
    "body": "${complete_changelog}",
    "draft": true,
    "prerelease": true
}
EOF
}

create_beta() {
    local drive_version

    drive_version="$(python tools/changelog.py --drive-version)"

    echo ">>> [beta ${drive_version}] Generating the changelog"
    changelog "${drive_version}"

    echo ">>> [beta ${drive_version}] Creating the tag"
    git tag -a "release-${drive_version}" -m "Release ${drive_version}"
    git push origin --tags
}

publish_beta() {
    local drive_version
    local artifacts

    drive_version="$(python tools/changelog.py --drive-version)"
    artifacts="https://qa.nuxeo.org/jenkins/view/Drive/job/Drive/job/Drive-packages/lastSuccessfulBuild/artifact/dist/*zip*/dist.zip"

    echo ">>> [beta ${drive_version}] Retrieving artifacts"
    [ -f dist.zip ] && rm -f dist.zip
    curl -L "$artifacts" -o dist.zip
    unzip -o dist.zip

    echo ">>> [beta ${drive_version}] Deploying to the staging website"
    rsync -vz dist/*${drive_version}* nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-tests/

    echo ">>> [beta ${drive_version}] Creating the GitHub pre-release"
    curl -X POST -i -n -d @draft.json https://api.github.com/repos/nuxeo/nuxeo-drive/releases
}

main() {
    if [ "$1" = "--create" ]; then
        create_beta
    elif [ "$1" = "--publish" ]; then
        publish_beta
    fi
}

main "$@"
