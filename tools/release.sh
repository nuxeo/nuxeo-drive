#!/bin/sh -eu
#
# Create a new release: it means creating a new beta, managing GitHub actions and
# deploying artifacts to the staging site.
#
# Warning: do not execute this script manually but from Jenkins.
#

export DRY_RUN="${DRY_RUN:=true}"

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

change_version() {
    local version
    local file

    version="$1"
    file="nuxeo-drive-client/nxdrive/__init__.py"
    rm -f ${file}
    echo "__version__ = '$version'" > ${file}
    git add ${file}
}

create_beta() {
    local version
    local drive_version
    local git_opt

    version="$(grep -Eo "[0-9]+.[0-9]+" nuxeo-drive-client/nxdrive/__init__.py | tr '\n' '\0')"
    drive_version="${version}.$(date +%-m%d)"

    if [ "${DRY_RUN}" = true ]; then
        git_opt="--dry-run"
    else
        git_opt=""
    fi

    echo ">>> [beta ${drive_version}] Creating the commit"
    change_version "${drive_version}"
    git commit -m "Release $drive_version"
    git push origin master ${git_opt}

    echo ">>> [beta ${drive_version}] Generating the changelog"
    changelog "${drive_version}"

    echo ">>> [beta ${drive_version}] Creating the tag"
    git tag "release-${drive_version}"
    git push origin --tags ${git_opt}
}

publish_beta() {
    local version
    local drive_version
    local artifacts
    local git_opt
    local rsync_opt

    version="$(grep -Eo "[0-9]+.[0-9]+" nuxeo-drive-client/nxdrive/__init__.py | tr '\n' '\0')"
    drive_version="$(grep -Eo "[0-9]+.[0-9]+.[0-9]+" nuxeo-drive-client/nxdrive/__init__.py | tr '\n' '\0')"
    artifacts="https://qa.nuxeo.org/jenkins/view/Drive/job/Drive/job/Drive-packages/lastSuccessfulBuild/artifact/dist/*zip*/dist.zip"
    rsync_opt="--verbose --compress"

    if [ "${DRY_RUN}" = true ]; then
        git_opt="--dry-run"
        rsync_opt="${rsync_opt} --dry-run"
    else
        git_opt=""
    fi

    echo ">>> [beta ${drive_version}] Creating the post commit"
    change_version "${version}-dev"
    git commit -m "Post release ${drive_version}"
    git push origin master ${git_opt}

    echo ">>> [beta ${drive_version}] Retrieving artifacts"
    [ -f dist.zip ] && rm -f dist.zip
    curl -L "$artifacts" -o dist.zip
    unzip -o dist.zip

    echo ">>> [beta ${drive_version}] Deploying to the staging website"
    rsync ${rsync_opt} dist/*${drive_version}* nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-tests/

    echo ">>> [beta ${drive_version}] Creating the GitHub pre-release"
    if [ "${DRY_RUN}" = true ]; then
        echo "DRY-RUN curl -X POST -i -n -d @draft.json https://api.github.com/repos/nuxeo/nuxeo-drive/releases"
        echo "DRY-RUN ============ draft.json start"
        cat draft.json
        echo "DRY-RUN ============ draft.json end"
    else
        curl -X POST -i -n -d @draft.json https://api.github.com/repos/nuxeo/nuxeo-drive/releases
    fi
}

main() {
    if [ "$1" = "--create" ]; then
        create_beta
    elif [ "$1" = "--publish" ]; then
        publish_beta
    fi
}

main "$@"
