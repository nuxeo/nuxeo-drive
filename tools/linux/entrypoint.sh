#!/usr/bin/env bash
set -e

if [ $# -gt 0 ]; then
    exec "$@"
else
    # On Jenkins, the current path will be the same as $WORKSPACE. If it is the case,
    # we already are into a cloned repository, so skipping the "git clone" step.
    if [ -z "${WORKSPACE}" ]; then
        export WORKSPACE="/opt"
        echo "[build n°${BUILD_VERSION}] git clone --depth=1 --branch ${BRANCH_NAME:-master} ${GIT_URL} sources"
        git clone --depth=1 --branch "${BRANCH_NAME:-master}" "${GIT_URL}" sources && cd sources
    fi

    ./tools/linux/deploy_jenkins_slave.sh --install-release
    ./tools/linux/deploy_jenkins_slave.sh --build

    # Running outside Jenkins, likely a local test
    if [ "$(pwd)" = "/opt/sources" ]; then
        echo "[build n°${BUILD_VERSION}] Copying interesting files into the volume"
        cp -v dist/*.AppImage /opt/dist
        cp -v dist/*.zip /opt/dist
    fi
fi
