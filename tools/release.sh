#!/bin/bash -eu
#
# Create a new release, it means:
#     - creating a new alpha or beta;
#     - managing GitHub actions;
#     - deploying artifacts to the staging site;
#
# Warning: do not execute this script manually but from Jenkins.
#

cancel() {
    # First argument is the release type (alpha or release)
    local release_type
    local drive_version

    release_type="$1"
    drive_version="$(python tools/changelog.py --drive-version)"

    echo ">>> [${release_type} ${drive_version}] Removing the tag"
    git tag --delete "${release_type}-${drive_version}" || true
    git push --delete origin "${release_type}-${drive_version}" || true

    echo ">>> [${release_type} ${drive_version}] Removing the branch"
    git branch -D "wip-alpha-${release_type}.${drive_version}" || true
    git push --delete origin "wip-alpha-${release_type}.${drive_version}" || true
}

changelog() {
    # Create the draft.json file with the pre-release content
    local drive_version
    local changelog

    drive_version="$1"
    changelog="$(cat <<EOF
$(python tools/changelog.py --format=md)

---

Download links:

- [GNU/Linux binary](https://community.nuxeo.com/static/drive-updates/beta/nuxeo-drive-${drive_version}-x86_64.AppImage)
- [macOS installer](https://community.nuxeo.com/static/drive-updates/beta/nuxeo-drive-${drive_version}.dmg)
- [Windows installer](https://community.nuxeo.com/static/drive-updates/beta/nuxeo-drive-${drive_version}.exe)
EOF
)"

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

create() {
    # First argument is the release type (alpha or release)
    local release_type
    local drive_version
    local alpha_version

    release_type="$1"

    if [ "${release_type}" = "alpha" ]; then
        # New alpha version:
        #    - checkout the last commit
        #    - update the version number and release date
        echo ">>> [${release_type}] Update information into a new branch"
        drive_version="$(python tools/changelog.py --drive-version)"
        alpha_version="$(git describe --always --match="release-*" | cut -d"-" -f3)"

        # Delete remote wip-alpha branch if it already exists and create a local one
        git push origin --delete "wip-alpha-${drive_version}.${alpha_version}" || true
        git checkout -b "wip-alpha-${drive_version}.${alpha_version}"

        # Set version number
        sed -i s"/^__version__ = \".*\"/__version__ = \"${drive_version}.${alpha_version}\"/" nxdrive/__init__.py
        sed -i s"/^Release date: \`.*\`/Release date: \`$(date '+%Y-%m-%d')\`/" "docs/changes/${drive_version}.md" || true
        git add nxdrive/__init__.py
        git add "docs/changes/${drive_version}.md" || true

        # Commit and push alpha branch
        git commit -m "Bump version to ${drive_version}.${alpha_version}"
        git push --set-upstream origin "wip-alpha-${drive_version}.${alpha_version}"
    fi

    drive_version="$(python tools/changelog.py --drive-version)"

    if [ "${release_type}" = "release" ]; then
        echo ">>> [${release_type} ${drive_version}] Generating the changelog"
        changelog "${drive_version}"
    fi

    echo ">>> [${release_type} ${drive_version}] Creating the tag"
    git tag -a "${release_type}-${drive_version}" -m "Release ${drive_version}"
    git push origin "${release_type}-${drive_version}"
}

publish() {
    # First argument is the release type (alpha or release)
    local release_type
    local drive_version
    local artifacts
    local path

    release_type="$1"
    drive_version="$(python tools/changelog.py --drive-version)"
    artifacts="https://qa.nuxeo.org/jenkins/view/Drive/job/Drive/job/Drive-packages/lastSuccessfulBuild/artifact/dist/*zip*/dist.zip"
    path="/var/www/community.nuxeo.com/static/drive-updates/"

    # The release_type is misinforming because it is "release" for beta and GA releases,
    # or "alpha" for alpha. To be review with NXDRIVE-1453.
    if [ "${release_type}" = "release" ]; then
        release_type="beta"
    fi

    echo ">>> [${release_type} ${drive_version}] Retrieving artifacts"
    [ -f dist.zip ] && rm -f dist.zip
    curl -L "$artifacts" -o dist.zip
    unzip -o dist.zip

    echo ">>> [${release_type} ${drive_version}] Generating ${drive_version}.yml"
    python -m pip install --user pyyaml==5.1.2
    python tools/versions.py --add "${drive_version}" --type "${release_type}"
    echo "\nContent of ${drive_version}.yml:"
    cat "${drive_version}.yml"

    echo ">>> [${release_type} ${drive_version}] Merging into versions.yml"
    rsync -vz nuxeo@lethe.nuxeo.com:"${path}versions.yml" .
    python tools/versions.py --merge
    echo "\nContent of versions.yml:"
    cat versions.yml

    echo "\n>>> [${release_type} ${drive_version}] Deploying to the staging website"
    rsync -vz dist/*${drive_version}* nuxeo@lethe.nuxeo.com:"${path}${release_type}/"
    rsync -vz versions.yml nuxeo@lethe.nuxeo.com:"${path}"

    if [ "${release_type}" = "beta" ]; then
        echo ">>> [${release_type} ${drive_version}] Creating the GitHub pre-release"
        curl -X POST -i -n -d @draft.json https://api.github.com/repos/nuxeo/nuxeo-drive/releases
    fi
}

main() {
    # $1 is the action to do
    # $2 is the release type (either alpha or release)
    case "$1" in
        "--cancel") cancel "$2" ;;
        "--create") create "$2" ;;
        "--publish") publish "$2" ;;
    esac
}

main "$@"
