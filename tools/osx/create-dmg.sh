#! /bin/bash

VOLUME_NAME="Nuxeo Drive"
APP_NAME="Nuxeo Drive.app"
SCRIPT_LOCATION="`dirname \"$0\"`"
OUTPUT_DIR="$SCRIPT_LOCATION/../../dist"
SRC_FOLDER_TEMP="$SCRIPT_LOCATION/dmg_src_folder.tmp"
DMG_TEMP="$SCRIPT_LOCATION/nuxeo-drive.tmp.dmg"
BACKGROUND_FILE="$SCRIPT_LOCATION/dmgbackground.png"
GENERATED_DS_STORE="$SCRIPT_LOCATION/generated_DS_Store"
SIGNING_IDENTITY="NUXEO CORP"

# Rename frozen app
mv "$OUTPUT_DIR/Nuxeo Drive"* "$OUTPUT_DIR/$APP_NAME"
PACKAGE_PATH="$OUTPUT_DIR/$APP_NAME"

# Get app version
APP_VERSION=$("$PACKAGE_PATH/Contents/MacOS/ndrive" -v 2>&1)
echo "$APP_NAME version is $APP_VERSION"

# Compute DMG name and size
FROZEN_APP="nuxeo-drive-$APP_VERSION-osx"
DMG_PATH="$OUTPUT_DIR/$FROZEN_APP.dmg"
DMG_SIZE=$(($(du -sm "$PACKAGE_PATH" | cut -d$'\t' -f1,1)+20))m

# Sign application bundle
codesign -s "$SIGNING_IDENTITY" "$PACKAGE_PATH" -v
# Verify code signature
codesign -vv "$PACKAGE_PATH"
codesign -d -vvv "$PACKAGE_PATH"
spctl --assess --type execute "$PACKAGE_PATH" --verbose

# Clean tmp directories
rm -rf "$SRC_FOLDER_TEMP" "$DMG_TEMP"
mkdir "$SRC_FOLDER_TEMP"

# Prepare DMG
cp -a "$PACKAGE_PATH" "$SRC_FOLDER_TEMP"
mkdir "$SRC_FOLDER_TEMP/.background"
cp "$BACKGROUND_FILE" "$SRC_FOLDER_TEMP/.background"
cp "$GENERATED_DS_STORE" "$SRC_FOLDER_TEMP/.DS_Store"
ln -s /Applications "$SRC_FOLDER_TEMP"

# Create DMG
hdiutil create -srcfolder "$SRC_FOLDER_TEMP" -volname "${VOLUME_NAME}" -fs HFS+ -fsargs "-c c=64,a=16,e=16" -format UDRW -size "${DMG_SIZE}" "${DMG_TEMP}"

rm -f "$DMG_PATH"
hdiutil convert "${DMG_TEMP}" -format UDZO -imagekey zlib-level=9 -o "${DMG_PATH}"

# Clean tmp directories
rm -rf "$SRC_FOLDER_TEMP" "$DMG_TEMP"

# Zip application bundle to make it available as an update package
echo "Zipping application bundle to make it available as an update"
zip -r "$OUTPUT_DIR/$FROZEN_APP.zip" "$PACKAGE_PATH"

