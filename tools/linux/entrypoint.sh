#!/usr/bin/env bash
set -e

if [ $# -gt 0 ]; then
    exec "$@"
else
    # Build the application
    echo "[build n°${BUILD_VERSION}] git clone --depth=1 --branch ${BRANCH_NAME:-master} ${GIT_URL} sources"
    git clone --depth=1 --branch "${BRANCH_NAME:-master}" "${GIT_URL}" sources && cd sources
    ./tools/linux/deploy_jenkins_slave.sh --install-release
    ./tools/linux/deploy_jenkins_slave.sh --build

    echo "[build n°${BUILD_VERSION}] Copying interesting binaries into the volume"
    sudo cp -v $(pwd)/dist/*.AppImage "${WORKSPACE}/dist"
    sudo cp -v $(pwd)/dist/*.zip "${WORKSPACE}/dist"
fi
