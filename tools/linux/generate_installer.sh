#!/bin/bash -e

# docker login
echo "${DOCKER_PASSWORD}" | docker login -u "${DOCKER_USERNAME}" --password-stdin "${REGISTRY}"

# For the volume to copy artifacts
mkdir build && chmod -R 777 build
mkdir dist && chmod -R 777 dist

# No auto-update check on GNU/Linux as AppImage cannot be started from headless agents, sadly.
# But this is not a big deal as the auto-update process on GNU/Linux is really a simple copy.

# Build the app
docker run -it -v "$(pwd)":/opt/sources "${REGISTRY}/${REPOSITORY}:py-3.9.5"  # XXX_PYTHON

# Ensure the AppImage is correct
bash tools/linux/deploy_ci_agent.sh --check

# Upload artifacts
for f in dist/*.AppImage; do
    bash tools/upload.sh staging "${f}"
done
