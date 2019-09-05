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

    # Move interesting binaries into the volume
    cp -v $(pwd)/dist/*.AppImage /opt/dist
    cp -v $(pwd)/dist/*.zip /opt/dist

    # Cleanup
    cd ..
    rm -rf sources
fi
