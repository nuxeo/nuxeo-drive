#!/bin/bash

set -e

# docker login
echo "${DOCKER_PASSWORD}" | docker login -u "${DOCKER_USERNAME}" --password-stdin docker-private.packages.nuxeo.com

# For the volume to copy artifacts
mkdir build && chmod -R 777 build
mkdir dist && chmod -R 777 dist

# No auto-update check on GNU/Linux as AppImage cannot be started from headless agents, sadly.
# But this is not a big deal as the auto-update process on GNU/Linux is really a simple copy.

# Build the app
docker run \
    -it \
    -v "$(pwd)":/opt/sources \
    docker-private.packages.nuxeo.com/nuxeo-drive-build:py-3.9.1  # XXX_PYTHON

# Ensure the AppImage is correct
bash tools/linux/deploy_ci_agent.sh --check

# Upload artifacts
for f in dist/*.AppImage; do
    bash tools/upload.sh staging "${f}"
done
