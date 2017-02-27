#!/bin/sh -eu

release() {
    local version="$(egrep -o "[0-9]+.[0-9]+" nuxeo-drive-client/nxdrive/__init__.py | tr '\n' '\0')"
    export DRIVE_VERSION="${version}.$(date +%-m%d)"

    echo ">>> [release ${DRIVE_VERSION}] Creating the release commit"
    sed -i "s/'.*'/'$DRIVE_VERSION'/" nuxeo-drive-client/nxdrive/__init__.py
    git commit -am "Release $DRIVE_VERSION"

    echo ">>> [release ${DRIVE_VERSION}] Creating the release tag"
    git tag release-${DRIVE_VERSION}

    echo ">>> [release ${DRIVE_VERSION}] Creating the post release commit"
    sed -i "s/'.*'/'${version}-dev'/" nuxeo-drive-client/nxdrive/__init__.py
    git commit -am "Post release ${DRIVE_VERSION}"

    echo ">>> [release ${DRIVE_VERSION}] Posting to GitHub"
    git push origin master
    git push --tags origin release-${DRIVE_VERSION}
}

deploy() {
    echo ">>> [release ${DRIVE_VERSION}] Deploying Nuxeo Drive"
    scp dist/*.deb dist/*.dmg dist/*.json dist/*.msi nuxeo@lethe.nuxeo.com:/var/www/community.nuxeo.com/static/drive/
}

main() {
    release
    deploy
}

main
