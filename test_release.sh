#!/bin/bash

if [ -z "$1" ]
  then
    echo "No argument supplied, please provide the new minor version."
    exit 1
fi

VIRTUALENV_DIR=ENV

if [ ! -d "$VIRTUALENV_DIR" ]; then
  echo "Please set up virtualenv in the $VIRTUALENV_DIR directory."
  exit 1
fi

UPDATE_SITE=dist
MAJOR_VERSION=1
MINOR_VERSION=$1
MONTH=$(date +"%m")
DAY=$(date +"%d")
VERSION=$MAJOR_VERSION.$MINOR_VERSION.$MONTH$DAY
DEV_VERSION=$MAJOR_VERSION.$MINOR_VERSION-dev

# Set version to $VERSION
echo "Setting version to $VERSION"
sed -i "s/'.*'/'$VERSION'/g" nuxeo-drive-client/nxdrive/__init__.py

# Freeze application and deploy it to update site
echo "Activating virtualenv"
source $VIRTUALENV_DIR/bin/activate
echo "Freezing application and deploying it to update site $UPDATE_SITE"
python setup.py bdist_esky --dev --freeze --enable-appdata-dir=True
echo "Setting back version to $DEV_VERSION"
sed -i "s/'.*'/'$DEV_VERSION'/g" nuxeo-drive-client/nxdrive/__init__.py

