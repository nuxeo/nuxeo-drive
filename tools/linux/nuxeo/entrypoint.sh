#!/usr/bin/env bash
#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

set -e

if [ $# -gt 0 ]; then
    exec "$@"
else
    export WORKSPACE="/opt"
    export WORKSPACE_DRIVE="/opt/sources"

    cd "${WORKSPACE_DRIVE}"
    ./tools/linux/deploy_ci_agent.sh --install-release
    ./tools/linux/deploy_ci_agent.sh --build-nuxeo
fi
