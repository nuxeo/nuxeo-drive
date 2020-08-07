#!/bin/bash
#
# Create a new release, it means:
#     - creating a new alpha or beta;
#     - deploying artifacts to the server;
#
# Warning: do not execute this script manually but from Travis-CI.
#

set -e

. "tools/env.sh"

cancel() {
    local artifacts

    artifacts="/var/www/community.nuxeo.com/static/drive-staging/${TRAVIS_BUILD_NUMBER}"

    echo ">>> [Deploy] Removing uploaded artifacts"
    ssh -o "StrictHostKeyChecking=no" nuxeo@lethe.nuxeo.com rm -rfv "${artifacts}"
}

create() {
    # First argument is the release type (alpha or beta)
    local drive_version
    local release_type

    drive_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
    release_type="$1"

    echo ">>> [${release_type} ${drive_version}] Creating the tag"
    git tag -f -a "${release_type}-${drive_version}" -m "Release ${drive_version}"
    git push -f origin "${release_type}-${drive_version}"
}

publish() {
    # First argument is the release type (alpha or beta)
    local artifacts
    local drive_version
    local release_type

    artifacts="/var/www/community.nuxeo.com/static/drive-staging/${TRAVIS_BUILD_NUMBER}"
    drive_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
    release_type="$1"

    echo ">>> [${release_type} ${drive_version}] Deploying to the server"
    scp -o "StrictHostKeyChecking=no" tools/versions.py nuxeo@lethe.nuxeo.com:"${artifacts}"
    ssh -o "StrictHostKeyChecking=no" -T nuxeo@lethe.nuxeo.com <<EOF
cd ${artifacts} || exit 1

echo " >> [Deploy] Generating ${drive_version}.yml"
export ARTIFACTS_FOLDER="./"
python3 versions.py --add "${drive_version}" --type "${release_type}" || exit 1
echo ""
echo "Content of ${drive_version}.yml:"
cat "${drive_version}.yml"

echo " >> [Deploy] Merging into versions.yml"
cp -v "${REMOTE_PATH_PROD}/versions.yml" . || exit 1
python3 versions.py --merge || exit 1
echo ""
echo "Content of versions.yml:"
cat versions.yml

echo ""
echo " >> [Deploy] Moving files"
mv -vf nuxeo-drive-${drive_version}* "${REMOTE_PATH_PROD}/${release_type}/" || exit 1
cp -vf versions.yml "${REMOTE_PATH_PROD}/" || exit 1

echo ""
echo " >> [Deploy] Clean-up"
cd ~
rm -rfv "${artifacts}"
EOF

}

main() {
    # $1 is the action to do
    # $2 is the release type (either alpha or beta)
    case "$1" in
        "--cancel") cancel "$2" ;;
        "--create") create "$2" ;;
        "--publish") publish "$2" ;;
    esac
}

main "$@"
