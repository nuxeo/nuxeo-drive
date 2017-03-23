#!/bin/sh -eu

export RELEASE_TYPE="${RELEASE_TYPE:=nightly}"

create_beta() {
    local version="$(egrep -o "[0-9]+.[0-9]+" nuxeo-drive-client/nxdrive/__init__.py | tr '\n' '\0')"
    local drive_version="${version}.$(date +%-m%d)"

    echo ">>> [beta ${drive_version}] Creating the commit"
    rm nuxeo-drive-client/nxdrive/__init__.py
    echo "__version__ = '$drive_version'\n" > nuxeo-drive-client/nxdrive/__init__.py
    git commit -am "Release $drive_version"

    echo ">>> [beta ${drive_version}] Creating the tag"
    git tag release-${drive_version}

    echo ">>> [beta ${drive_version}] Creating the post commit"
    rm nuxeo-drive-client/nxdrive/__init__.py
    echo "__version__ = '${version}-dev'\n" > nuxeo-drive-client/nxdrive/__init__.py
    git commit -am "Post release ${drive_version}"

    echo ">>> [beta ${drive_version}] Pushing to GitHub"
    git push origin master
    git push --tags origin release-${drive_version}

    echo ">>> [beta ${drive_version}] Deploying to the staging website"
    # TODO: Where are the files?!
    scp dist/*.deb dist/*.dmg dist/*.json dist/*.msi dist/*.zip nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive-tests/

    # TODO: create changelog
    # TODO: create GitHub pre-release
}

get_lastest_release_tag() {
    git fetch --tags
    git rev-list --tags --remove-empty --branches=master --max-count=10 | while read commit_id; do
        desc=$(git describe --abbrev=0 --tags ${commit_id})
        case ${desc} in
            release-*)
                echo ${desc}
                break ;;
        esac
    done
}

release() {
    local lastest_release=$(get_lastest_release_tag)
    local drive_version=$(echo ${lastest_release} | cut -d'-' -f2)

    if [ "${drive_version}" = '' ]; then
        echo ">>> No Drive version found."
        exit 1
    fi

    echo ">>> [release ${drive_version}] Deploying to the production website"
    ssh nuxeo@lethe.nuxeo.com "cp -vf /var/www/community.nuxeo.com/static/drive-tests/*${drive_version}* /var/www/community.nuxeo.com/static/drive/"

    echo ">>> [release ${drive_version}] Uploading to PyPi"
    git checkout tags/${lastest_release}
    python setup.py sdist upload

    # TODO: convert GitHub pre-release to release
    # TODO: Slack notification?
}

main() {
    echo ">>> Release type: ${RELEASE_TYPE}"

    if [ "${RELEASE_TYPE}" = "release" ]; then
        release
    elif [ "${RELEASE_TYPE}" = "beta" ]; then
        create_beta
    else
        exit 1
    fi
}

main
