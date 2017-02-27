#!/bin/bash -xe

GIT_DESC=`git describe --all`
BRANCH=${GIT_DESC#*/}
MAJOR_VERSION=${MAJOR_VERSION:-$1}
MINOR_VERSION=${MINOR_VERSION:-$2}
RELEASE_VERSION=${RELEASE_VERSION:-$3}

[ -n "$MAJOR_VERSION" ]
[ -n "$MINOR_VERSION" ]
[ -n "$RELEASE_VERSION" ]

# Release version
VERSION=$MAJOR_VERSION.$MINOR_VERSION.$RELEASE_VERSION

# Release commit
echo Do release commit
sed -i "s/'.*'/'$VERSION'/g" nuxeo-drive-client/nxdrive/__init__.py
git commit -am"Release $VERSION"

# Release tag
echo Do release tag
git tag -f release-$VERSION

# Post release commit
echo Do post release commit
sed -i "s/'.*'/'$MAJOR_VERSION.$MINOR_VERSION-dev'/g" nuxeo-drive-client/nxdrive/__init__.py
git commit -am"Post release $VERSION"

# Push to GitHub
git push origin $BRANCH
git push -f --tags origin release-$VERSION

