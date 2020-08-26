#!/bin/bash

set -e

# The certificate
echo "${CERT_APP_WINDOWS}" | base64 --decode > certificate.pfx

# PowerShell unlocking
powershell Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope LocalMachine

# Install required stuff
powershell ".\\tools\\windows\\deploy_ci_agent.ps1" -install_release

# Test the auto-updater
powershell ".\\tools\\windows\\deploy_ci_agent.ps1" -check_upgrade

# Build the app
rm -rf build dist
powershell ".\\tools\\windows\\deploy_ci_agent.ps1" -build

# Upload artifacts
for f in dist/*.exe; do
    bash tools/upload.sh staging "${f}"
done
