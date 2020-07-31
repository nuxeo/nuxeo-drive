#!/bin/bash -eu
#
# Delete old alpha releases.
#

purge() {
    # $1: the version to remove
    local version
    local path

    version="$1"
    path="/var/www/community.nuxeo.com/static/drive-updates"

    echo " - ${version}"
    python3 tools/versions.py --delete "${version}"
    ssh -o StrictHostKeyChecking=no -T nuxeo@lethe.nuxeo.com "rm -vf ${path}/alpha/*${version}.* ${path}/alpha/*${version}-*" || true
    git tag --delete "alpha-${version}" || true
    git push --delete origin "wip-alpha-${version}" || true  # branch
    git push --delete origin "alpha-${version}" || true  # tag
}

main() {
    # $1 is an optional version to delete
    local path
    local release

    path="/var/www/community.nuxeo.com/static/drive-updates"

    echo ">>> Installing requirements"
    python3 -m pip install --user pyyaml==5.3.1

    echo ">>> Retrieving versions.yml"
    rsync -e "ssh -o StrictHostKeyChecking=no" -vz nuxeo@lethe.nuxeo.com:"${path}/versions.yml" .

    echo ">>> Checking versions.yml integrity"
    python3 tools/versions.py --check || exit 1

    if [ -n "$1" ]; then
        if [ $(echo "$1" | tr -d -c '.' | wc -c) -gt 2 ]; then
            echo ">>> Removing alpha version $1"
            purge "$1"
        else
            echo " !! Invalid version number: $1 (not alpha)"
            exit 0
        fi
    else
        echo ">>> Removing alpha versions older than 21 days"
        while IFS= read release; do
            purge "$(echo ${release} | sed s'/alpha-//')"
        done < <(git tag -l "alpha-*" --sort=-taggerdate | tail -n +21)
    fi

    echo ">>> Checking versions.yml integrity"
    python3 tools/versions.py --check || exit 1

    echo ">>> Uploading versions.yml"
    rsync -e "ssh -o StrictHostKeyChecking=no" -vz versions.yml nuxeo@lethe.nuxeo.com:"${path}/"
}

main "$@"
