#!/bin/bash -eu
#
# Upload a file to a server.
# It is using the $GITHUB_RUN_NUMBER envar to differentiate different files.
#

. "tools/env.sh"

publish_staging() {
    # First argument is the file (artifact) to upload
    local artifact
    local path

    artifact="$1"
    path="${REMOTE_PATH_STAGING}/${GITHUB_RUN_NUMBER}/"

    echo ">>> [Upload] Deploying to the staging server"
    rsync -e "ssh -o StrictHostKeyChecking=no" --chmod=755 -pvz "${artifact}" nuxeo@lethe.nuxeo.com:"${path}" || \
        rsync -e "ssh -o StrictHostKeyChecking=no" -vz "${artifact}" nuxeo@lethe.nuxeo.com:"${path}" || exit 1  # macOS does not have --chmod
    echo "Artifacts deployed to:"
    echo " >>> ${REMOTE_PATH_STAGING}/${GITHUB_RUN_NUMBER} <<<"
}

main() {
    # $1 is server type (staging, production, ...)
    # $2 is the file to upload
    case "$1" in
        "staging") publish_staging "$2" ;;
    esac
}

main "$@"
