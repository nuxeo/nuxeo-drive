#!/bin/bash

set -e

# Certificates
wget https://www.apple.com/appleca/AppleIncRootCertificate.cer
echo "${CERT_APP_MACOS}" | base64 --decode > developerID_application.cer
echo "${PRIV_APP_MACOS}" | base64 --decode > nuxeo-drive.priv

# Install required stuff
bash tools/osx/deploy_jenkins_slave.sh --install-release

# Test the auto-updater
bash tools/osx/deploy_jenkins_slave.sh --check-upgrade

# Build the app
rm -rf build dist
bash tools/osx/deploy_jenkins_slave.sh --build

# Upload artifacts
for f in dist/*.dmg; do
    bash tools/upload.sh staging "${f}"
done
