#!/bin/bash -e

# For the volume to copy artifacts
mkdir build && chmod -R 777 build
mkdir dist && chmod -R 777 dist

# No auto-update check on GNU/Linux as AppImage cannot be started from headless agents, sadly.
# But this is not a big deal as the auto-update process on GNU/Linux is really a simple copy.

# Build the app
# Note: the "-it" argument cannot be used on GitHub-CI (https://stackoverflow.com/a/43099210/1117028)
#       and is not needed anyway.
docker run --rm -v "$(pwd)":/opt/sources "${REGISTRY}/${REPOSITORY}:py-3.9.5" || exit 1  # XXX_PYTHON

# Ensure the AppImage is correct
bash tools/linux/deploy_ci_agent.sh --check || exit 1
