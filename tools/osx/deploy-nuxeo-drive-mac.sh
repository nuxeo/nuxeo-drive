#!/bin/bash
#
# Usage: bash deploy-nuxeo-drive-mac.sh VERSION
#
# Deploy script for Nuxeo Drive releases (not alpha, not beta, just official releases).
#
# Workflow:
#   - kill eventual running process
#   - uninstall any versions in /Applications and $HOME/Applications
#   - download the given version
#   - install the given version
#   - add a custom local config file
#
# Contributors:
#   - Mickaël Schoentgen <mschoentgen@nuxeo.com>
#
# History:
#
#   1.0.0 [2020-02-13]
#       - Initial version.
#

set -e

# Global variables
VERSION="1.0.0"
APP="Nuxeo Drive"
URL="https://community.nuxeo.com/static/drive-updates/release/nuxeo-drive"
TMPDIR="$(mktemp -d)"
INSTALLER="${TMPDIR}/installer.dmg"

add_local_config() {
    # Add a custom config file (a backup is done)
    local version="${1}"
    local conf="$HOME/.nuxeo-drive/config.ini"
    local data="[DEFAULT]
env = managed

[managed]
channel = centralized
"

    if [ "${version}" = "4.4.0" ]; then
        # On 4.4.0 we need to enforce client_version locally.
        # See https://jira.nuxeo.com/browse/NXDRIVE-2047 for details.
        data="${data}client_version = ${version}\n"
    fi

    echo ">>> Disabling auto-updates in the config file"

    if test -f "${conf}"; then
        # Backup the current file, the user will have to merge old and new files manually
        echo ">>> Backing up current ${conf} file, manual merge will be needed"
        mv "${conf}" "${conf}.$(date '+%Y_%m_%d-%H_%M_%S')"
    fi

    # Create the conf file
    printf "${data}" >"${conf}"
}

download() {
    # Download the given installer version.
    local url="${URL}-${1}.dmg"

    echo ">>> Downloading ${url}"
    echo "    -> ${INSTALLER}"
    curl "${url}" > "${INSTALLER}"
}

force_kill() {
    # Kill any running process.
    pkill "ndrive" && echo ">>> Killed running process" || true
}

install() {
    # Install the given version.
    echo ">>> Installing ${APP}"

    # The user's Application folder does not exist by default, let's create it
    if ! test -d "$HOME/Applications"; then
        mkdir "$HOME/Applications"
        echo "Created $HOME/Applications"
    fi

    # Fix the notarization (enforced security since February 2020)
    xattr -d com.apple.quarantine "${INSTALLER}" 2>/dev/null

    # Mount the DMG
    # The awk part will split the line each 2 or more spaces as the volume path may contain 1 space
    mount_dir="$(hdiutil mount "${INSTALLER}" | tail -1 | awk -F '[[:space:]][[:space:]]+' {'print $3'})"

    # Do the copy inside the user's Applications folder
    echo ">>> Copying ${mount_dir}/${APP}.app contents"
    echo "    -> $HOME/Applications"
    cp -rf "${mount_dir}/${APP}.app" "$HOME/Applications"

    # Fix the notarization (enforced security since February 2020)
    xattr -d com.apple.quarantine "$HOME/Applications/${APP}.app" 2>/dev/null

    # Unmount the DMG, do not fail at this step
    hdiutil unmount -force "${mount_dir}" >/dev/null || true
}

uninstall() {
    # Remove any installed versions.
    local folder
    local app

    # Remove potential applications from /Applications and $HOME/Applications
    for folder in /Applications $HOME/Applications; do
        app="${folder}/${APP}.app"
        if test -d "${app}"; then
            /bin/rm -rf "${app}"
            echo ">>> Uninstalled ${app}"
        fi
    done
}

main() {
    # Entry point
    echo "${APP} deploy script, version ${VERSION}."
    echo

    if [ $# -ne 1 ]; then
        echo "Usage: $0 VERSION (must be >= 4.4.0)"
        echo "Ex:    $0 4.4.0"
        exit 1
    fi

    local version="${1}"

    echo ">>> Deploying ${APP} ${version} ... "

    force_kill
    uninstall
    download "${version}"
    install
    add_local_config "${version}"

    # Clean-up
    rm -rf "${TMPDIR}" || true

    echo ">>> ${APP} ${version} successfully deployed!"
}

main $@
