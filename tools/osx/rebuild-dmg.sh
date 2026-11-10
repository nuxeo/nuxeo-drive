#!/bin/bash
#
# Kill Nuxeo Drive, remove old DMG artifacts, and rebuild the macOS package.
#
# Usage:
#   ./tools/osx/rebuild-dmg.sh
#
# Optional environment variables:
#   WORKSPACE       Parent workspace directory (defaults to the repo parent).
#   WORKSPACE_DRIVE Path to the nuxeo-drive checkout (defaults to repo root).
#
# Example:
#   export WORKSPACE="/Users/amit.hembrom/Workspace/Drive/master"
#   ./tools/osx/rebuild-dmg.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [ -z "${WORKSPACE:-}" ]; then
    export WORKSPACE="$(dirname "${REPO_ROOT}")"
fi
export WORKSPACE_DRIVE="${WORKSPACE_DRIVE:-${REPO_ROOT}}"

echo ">>> WORKSPACE       = ${WORKSPACE}"
echo ">>> WORKSPACE_DRIVE = ${WORKSPACE_DRIVE}"

echo ">>> Killing Nuxeo Drive..."
pkill -f "Nuxeo Drive.app/Contents/MacOS/ndrive" 2>/dev/null || true
pkill -x ndrive 2>/dev/null || true
sleep 1

echo ">>> Detaching mounted DMG volumes..."
for volume in /Volumes/Nuxeo\ Drive*; do
    if [ -d "${volume}" ]; then
        hdiutil detach "${volume}" -force >/dev/null 2>&1 \
            && echo "    detached: ${volume}" \
            || echo "    could not detach: ${volume}"
    fi
done

echo ">>> Removing old DMG files..."
rm -fv "${REPO_ROOT}"/dist/nuxeo-drive-*.dmg 2>/dev/null || true
rm -fv "${WORKSPACE}"/nuxeo-drive.tmp.dmg 2>/dev/null || true
rm -rf "${WORKSPACE}"/dmg_src_folder.tmp 2>/dev/null || true

echo ">>> Removing old app from ~/Applications..."

rm -rf "${APP_DST}"

echo ">>> Building..."
cd "${REPO_ROOT}"
./tools/osx/deploy_ci_agent.sh --build-nuxeo

APP_SRC="${REPO_ROOT}/dist/Nuxeo Drive.app"
APP_DST="${HOME}/Applications/Nuxeo Drive.app"
DMG_PATH="${REPO_ROOT}/dist/nuxeo-drive-"*.dmg

if [ -d "${APP_SRC}" ]; then
    echo ">>> Installing to ${APP_DST}"
    rm -rf "${APP_DST}"
    cp -R "${APP_SRC}" "${APP_DST}"
elif ls ${DMG_PATH} 1>/dev/null 2>&1; then
    DMG_FILE="$(ls -t ${DMG_PATH} | head -1)"
    MOUNT_POINT="/Volumes/Nuxeo Drive"
    echo ">>> Extracting app from ${DMG_FILE}"
    hdiutil attach "${DMG_FILE}" -nobrowse -quiet
    rm -rf "${APP_DST}"
    cp -R "${MOUNT_POINT}/Nuxeo Drive.app" "${APP_DST}"
    hdiutil detach "${MOUNT_POINT}" -quiet
else
    echo ">>> WARNING: No app bundle or DMG found in dist/"
fi

if [ -d "${APP_DST}" ]; then
    if rg -q "Loader" "${APP_DST}/Contents/Resources/data/qml/Main.qml" 2>/dev/null; then
        echo ">>> WARNING: Main.qml still contains Loader — wrong build!"
        exit 1
    fi
    echo ">>> Installed. Launch: open \"${APP_DST}\""
else
    echo ">>> WARNING: Install failed — copy Nuxeo Drive.app to ~/Applications manually."
fi
pkill -9 ndrive 2>/dev/null || true
open "$HOME/Applications/Nuxeo Drive.app"

echo ">>> Done."
