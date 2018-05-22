#!/bin/sh -eu
#
# Create a new release, it means:
#     - creating a new beta;
#     - managing GitHub actions;
#     - deploying artifacts to the staging site;
#
# Warning: do not execute this script manually but from Jenkins.
#

cancel_beta() {
    local drive_version

    drive_version="$(python tools/changelog.py --drive-version)"

    echo ">>> [beta ${drive_version}] Removing the release tag"
    git tag --delete "release-${drive_version}" || true
    git push --delete origin "release-${drive_version}" || true
}

changelog() {
    # Create the draft.json file with the pre-release content
    local drive_version
    local changelog

    drive_version="$1"
    changelog="$(python tools/changelog.py --format=md)"

    # Escape lines feed and double quotes for JSON
    changelog="$(echo "${changelog}" | sed 's|$|\\n|g ; s|\"|\\\"|g')"

    # Create the pre-release draft
    [ -f draft.json ] && rm -f draft.json
    cat > draft.json <<EOF
{
    "tag_name": "release-${drive_version}",
    "name": "${drive_version}",
    "body": "${changelog}",
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

    echo ">>> [beta ${drive_version}] Generating ${drive_version}.yml"
    python -m pip install --user pyaml==17.12.1
    python tools/versions.py --add "beta-${drive_version}"

    echo ">>> [beta ${drive_version}] Merging into versions.yml"
    rsync -vz nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-updates/versions.yml .
    pwd
    ls
    python tools/versions.py --merge

    echo ">>> [beta ${drive_version}] Deploying to the staging website"
    rsync -vz dist/*${drive_version}* nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-updates/beta/
    rsync -vz versions.yml nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-updates/

    echo ">>> [beta ${drive_version}] Creating the GitHub pre-release"
    curl -X POST -i -n -d @draft.json https://api.github.com/repos/nuxeo/nuxeo-drive/releases
}

main() {
    if [ $# -eq 1 ]; then
        case "$1" in
            "--cancel") cancel_beta ;;
            "--create") create_beta ;;
            "--publish") publish_beta ;;
        esac
    fi
}

main "$@"
