#!/usr/bin/env bash
set -e

if [ $# -gt 0 ]; then
    exec "$@"
else
    export WORKSPACE="/opt"
    export WORKSPACE_DRIVE="/opt/sources"
    export PIP_CONFIG_FILE="${PIP_CONFIG_FILE}"

    cd "${WORKSPACE_DRIVE}"
    ./tools/linux/deploy_ci_agent.sh --install-release
    ./tools/linux/deploy_ci_agent.sh --build
fi
