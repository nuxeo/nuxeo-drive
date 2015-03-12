#!/bin/bash

if [ -z "$1" ]
  then
    echo "No argument supplied, please provide the current minor version."
    exit 1
fi

VIRTUALENV_DIR=ENV

if [ ! -d "$VIRTUALENV_DIR" ]; then
  echo "Please set up virtualenv in the $VIRTUALENV_DIR directory."
  exit 1
fi

INSTALL_DIR=~/freeze
UPDATE_SITE=dist
APP_NAME=nuxeo-drive
MAJOR_VERSION=2
MINOR_VERSION=$1
MONTH=$(date +"%m")
DAY=$(date +"%d")
VERSION=$MAJOR_VERSION.$MINOR_VERSION.$MONTH$DAY
DEV_VERSION=$MAJOR_VERSION.$MINOR_VERSION-dev
PLATFORM=linux-x86_64
FREEZE_EXTENSION=zip
FROZEN_APP=$APP_NAME-$VERSION.$PLATFORM.$FREEZE_EXTENSION
EXECUTABLE=ndrive

# Delete Nuxeo Drive configuration and files
#echo "Deleting Nuxeo Drive configuration and files"
#rm -rf ~/.nuxeo-drive/ ~/Nuxeo\ Drive/

# Delete installed frozen applications
echo "Deleting frozen applications installed in $INSTALL_DIR"
rm -rf $INSTALL_DIR/*

# Delete frozen applications from update site
echo "Deleting frozen applications from update site $UPDATE_SITE"
rm $UPDATE_SITE/$MAJOR_VERSION.*.json
rm -rf $UPDATE_SITE/$APP_NAME-*

# Set version to $VERSION
echo "Setting version to $VERSION"
sed -i "s/'.*'/'$VERSION'/g" nuxeo-drive-client/nxdrive/__init__.py

# Freeze application and deploy it to update site
echo "Activating virtualenv"
source $VIRTUALENV_DIR/bin/activate
echo "Installing requirements"
pip install -r requirements.txt
pip install -r unix-requirements.txt
echo "Freezing application and deploying it to update site $UPDATE_SITE"
python setup.py --freeze bdist_esky --rm-freeze-dir-after-zipping=True
echo "Setting back version to $DEV_VERSION"
sed -i "s/'.*'/'$DEV_VERSION'/g" nuxeo-drive-client/nxdrive/__init__.py

# Install frozen application
echo "Unzipping $UPDATE_SITE/$FROZEN_APP to $INSTALL_DIR"
unzip $UPDATE_SITE/$FROZEN_APP -d $INSTALL_DIR

# Launch installed frozen application
echo "Launching frozen application: $INSTALL_DIR/$EXECUTABLE"
$INSTALL_DIR/$EXECUTABLE --log-level-console=DEBUG --update-check-delay=3 --update-site-url=http://localhost:8001/dist

