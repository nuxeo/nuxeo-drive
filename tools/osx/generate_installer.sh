#!/bin/bash

set -e

# Install required stuff
bash tools/osx/deploy_ci_agent.sh --install-release

# Test the auto-updater
rm -rf build dist
bash tools/osx/deploy_ci_agent.sh --check-upgrade

# Upload artifacts
for f in dist/*.dmg; do
    bash tools/upload.sh staging "${f}"
done
