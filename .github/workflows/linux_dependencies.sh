#!/bin/bash
#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

set -e

# Linux dependencies for Qt/QML
DEPENDENCIES=(
    libegl1
    libopengl0
)

sudo apt-get update
sudo apt-get install -y "${DEPENDENCIES[@]}"
