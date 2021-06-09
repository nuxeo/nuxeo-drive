#!/bin/bash -eu
#
# Delete old alpha releases.
#

. "tools/env.sh"

purge() {
    # $1: the version to remove
    local version

    version="$1"

    echo " - ${version}"
    python3 tools/versions.py --delete "${version}"
    ssh -o StrictHostKeyChecking=no -T nuxeo@lethe.nuxeo.com "rm -vf ${REMOTE_PATH_PROD}/alpha/*${version}.* ${REMOTE_PATH_PROD}/alpha/*${version}-*" || true
    git tag --delete "alpha-${version}" || true
    git push --delete origin "wip-alpha-${version}" || true  # branch
    git push --delete origin "alpha-${version}" || true  # tag
}

main() {
    # $1 is an optional version to delete
    local current_date
    local days
    local release
    local release_date
    local version

    echo ">>> Installing requirements"
    python3 -m pip install --user -U setuptools wheel
    python3 -m pip install --user pyyaml==5.3.1

    echo ">>> Retrieving versions.yml"
    rsync -e "ssh -o StrictHostKeyChecking=no" -vz nuxeo@lethe.nuxeo.com:"${REMOTE_PATH_PROD}/versions.yml" .

    echo ">>> Checking versions.yml integrity"
    python3 tools/versions.py --check || exit 1
    md5sum versions.yml > hash.md5

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
        current_date=$(date -d "00:00" +%s)
        while IFS= read -r release; do
            release_date=$(date -d $(echo "${release}" | cut -d' ' -f2)  +%s)
            days=$(( (current_date - release_date) / (24*3600) ))
            if [ ${days} -gt 21 ]; then
                version="$(echo "${release}" | cut -d' ' -f1 | sed s'/alpha-//')"
                purge "${version}"
            fi
        done < <(git for-each-ref --sort=-taggerdate --format '%(refname:short) %(taggerdate:short)' refs/tags | grep -E "(^alpha*)")
    fi

    if md5sum -c --status hash.md5; then
        echo ">>> No changes in versions.yml, good."
        return 0
    fi

    echo ">>> Checking versions.yml integrity"
    python3 tools/versions.py --check || exit 1

    echo ">>> Uploading versions.yml"
    rsync -e "ssh -o StrictHostKeyChecking=no" -vz versions.yml nuxeo@lethe.nuxeo.com:"${REMOTE_PATH_PROD}/"
}

main "$@"
