#!/bin/sh -eu
#
# Delete old alpha releases.
#
# Warning: do not execute this script manually but from Jenkins.
#

main() {
    local cmd
    local number
    local older_than
    local path
    local release
    local version

    number=0
    older_than=21
    path="/var/www/community.nuxeo.com/static/drive-updates/"
    cmd=$(git tag -l "alpha-*" --sort=-taggerdate | tail -n +${older_than})

    echo ">>> Installing requirements"
    python -m pip install --user pyaml==17.12.1

    echo ">>> Retrieving versions.yml"
    rsync -vz nuxeo@lethe.nuxeo.com:${path}/versions.yml .

    echo ">>> Checking versions.yml integrity"
    python tools/versions.py --check || exit 1

    echo ">>> Removing alpha versions older than ${older_than} days"
    for release in ${cmd}; do
        version="$(echo ${release} | sed s'/alpha-//')"
        echo " - ${version}"
        python tools/versions.py --delete "${version}"
    done

    echo ">>> Checking versions.yml integrity"
    python tools/versions.py --check || exit 1

    echo ">>> Uploading versions.yml"
    rsync -vz versions.yml nuxeo@lethe.nuxeo.com:${path}

    echo ">>> Removing binaries and tags:"
    for release in ${cmd}; do
        version="$(echo ${release} | sed s'/alpha-//')"
        echo " - ${version}"
        ssh -T nuxeo@lethe.nuxeo.com "rm -vf ${path}/alpha/*${version}*"
        git tag --delete "${release}"
        git push --delete origin "${release}"
    done
}

main
