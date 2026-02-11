#!/bin/bash
set -e

# Linux dependencies for Qt/QML
DEPENDENCIES=(
    libegl1
    libopengl0
)

sudo apt-get update
sudo apt-get install -y "${DEPENDENCIES[@]}"
