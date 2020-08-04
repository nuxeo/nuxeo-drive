#!/usr/bin/env bash
set -e

if [ $# -gt 0 ]; then
    exec "$@"
else
    export WORKSPACE="/opt"
    export WORKSPACE_DRIVE="/opt/sources"

    cd "${WORKSPACE_DRIVE}"
    ./tools/linux/deploy_jenkins_slave.sh --install-release
    ./tools/linux/deploy_jenkins_slave.sh --build
fi
