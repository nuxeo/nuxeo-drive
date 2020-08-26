#! /bin/bash
# Script to generate the .DS_Store file of the .dmg
# The execution of this script does not work without an active graphical user session
# hence cannot be run remotely by ssh as done on the Jenkins agent.
# Therefore the result of this script is checked in under version control.
set -ex
VOLUME_NAME="Nuxeo Drive"
DMG_SIZE=50m

SCRIPT_LOCATION="`dirname \"$0\"`"
BACKGROUND_FILE=$SCRIPT_LOCATION/dmgbackground.png
GENERATED_DS_STORE="$SCRIPT_LOCATION/generated_DS_Store"
DMG_TEMP="$SCRIPT_LOCATION/nuxeo-drive.tmp.dmg"

PACKAGE_PATH="$SCRIPT_LOCATION/../../dist/Nuxeo Drive.app"
SRC_FOLDER=$(dirname "$PACKAGE_PATH")
PACKAGE_NAME=$(basename "$PACKAGE_PATH")
BACKGROUND_FILE_NAME="$(basename $BACKGROUND_FILE)"

# Create the image
echo "Creating disk image..."
test -f "${DMG_TEMP}" && rm -f "${DMG_TEMP}"
hdiutil create -srcfolder "$SRC_FOLDER" -volname "${VOLUME_NAME}" -fs HFS+ -fsargs "-c c=64,a=16,e=16" -format UDRW -size "${DMG_SIZE}" "${DMG_TEMP}"
device=$(hdiutil attach -readwrite -noverify -noautoopen "${DMG_TEMP}" | egrep '^/dev/' | sed 1q | awk '{print $1}')

# Copy background image
mkdir /Volumes/"${VOLUME_NAME}"/.background
cp $BACKGROUND_FILE /Volumes/"${VOLUME_NAME}"/.background/"${BACKGROUND_FILE_NAME}"

# Symlink to the Applications folder
ln -s /Applications /Volumes/"$VOLUME_NAME"/Applications

# Set background image + icon size + icon position
# XXX: the close/open after icon positioning is to circumvent a bug in Snow
# Leopard. Without it, the icon position is not changed
echo '
   tell application "Finder"
       tell disk "'"${VOLUME_NAME}"'"
	       open
	       set current view of container window to icon view
	       set toolbar visible of container window to false
	       set statusbar visible of container window to false
	       set the bounds of container window to {100, 100, 700, 350}
	       set theViewOptions to the icon view options of container window
	       set arrangement of theViewOptions to not arranged
	       set icon size of theViewOptions to 128
	       set background picture of theViewOptions to file ".background:'${BACKGROUND_FILE_NAME}'"
	       set position of item "'${PACKAGE_NAME}'" of container window to {150, 110}
	       set position of item "Applications" of container window to {450, 110}
	       close
	       open
	       update without registering applications
	       delay 5
       end tell
   end tell
' | osascript
sync
sync
chmod -Rf go-w /Volumes/"${VOLUME_NAME}"/.DS_Store
cp -a /Volumes/"${VOLUME_NAME}"/.DS_Store "$GENERATED_DS_STORE"
hdiutil detach ${device}
rm -f "${DMG_TEMP}"
