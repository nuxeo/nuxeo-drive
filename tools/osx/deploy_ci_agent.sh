#!/bin/bash
# See tools/posix/deploy_ci_agent.sh for more information and arguments.

set -e

export OSI="osx"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/osx/', '/posix/'))")"


# Global variables
CODESIGN="codesign                              \
    --options runtime                           \
    --timestamp                                 \
    --entitlements tools/osx/entitlements.plist \
    --sign"

prepare_signing() {
    # Get the identity for code signing the app
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-OSX-Code-Signing

    if [ "${SIGNING_ID:-unset}" = "unset" ]; then
        echo ">>> [sign] WARNING: Signing ID is unavailable, application won't be signed."
        return
    elif [ "${KEYCHAIN_PASSWORD:-unset}" = "unset" ]; then
        echo ">>> [sign] WARNING: Keychain is unavailable, application won't be signed."
        return
    fi

    echo ">>> [sign] Unlocking the keychain"
    security unlock-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    # Allow to use the codesign executable
    security set-key-partition-list -S apple-tool:,apple: -s -k "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    security find-identity -p codesigning -v "${KEYCHAIN_PATH}" | grep "${SIGNING_ID}" || (
        echo "The '${SIGNING_ID}' identity is not available or no more valid."
        echo "This is the identities list:"
        security find-identity -p codesigning "${KEYCHAIN_PATH}"
        exit 1
    )
}

prepare_signing_from_scratch() {
    # Create and get the identity for code signing the app
    # http://www.tiger-222.fr/?d=2019/11/06/09/40/43-installer-un-certificat-pour-la-signature-de-code-automatique-macos
    # https://docs.travis-ci.com/user/common-build-problems/#mac-macos-sierra-1012-code-signing-errors

    if security list-keychains | grep -q "$(basename "${KEYCHAIN_PATH}")"; then
        # Already created at a previous run
        prepare_signing
        return
    fi

    echo ">>> [sign] Create the keychain"
    security create-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    echo ">>> [sign] Make the custom keychain default, so xcodebuild will use it for signing"
    security default-keychain -s "${KEYCHAIN_PATH}"

    echo ">>> [sign] Unlock the keychain"
    security unlock-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"

    echo ">>> [sign] Add certificates to keychain and allow codesign to access them"
    security import ./AppleIncRootCertificate.cer -t cert -A -k "${KEYCHAIN_PATH}"
    security import ./developerID_application.cer -t cert -A -T /usr/bin/codesign -k "${KEYCHAIN_PATH}"
    security import ./nuxeo-drive.priv -t priv -A -T /usr/bin/codesign -k "${KEYCHAIN_PATH}"

    prepare_signing
}

build_extension() {
    # Create the FinderSync extension, if not already done
    local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive"

    echo ">>> [package] Building the FinderSync extension"
    xcodebuild -project "${extension_path}/drive.xcodeproj" -target "NuxeoFinderSync" -configuration Release build
    mv -fv "${extension_path}/build/Release/NuxeoFinderSync.appex" "${WORKSPACE_DRIVE}/NuxeoFinderSync.appex"
    rm -rf "${extension_path}/build"
}

create_package() {
    # Create the final DMG
    local app_name="Nuxeo Drive"
    local bundle_name="${app_name}.app"
    local output_dir="${WORKSPACE_DRIVE}/dist"
    local pkg_path="${output_dir}/${bundle_name}"
    local src_folder_tmp="${WORKSPACE}/dmg_src_folder.tmp"
    local dmg_tmp="${WORKSPACE}/nuxeo-drive.tmp.dmg"
    local background_file="${WORKSPACE_DRIVE}/tools/osx/dmgbackground.png"
    local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive"
    local entitlements="${extension_path}/NuxeoFinderSync/NuxeoFinderSync.entitlements"
    local generated_ds_store="${WORKSPACE_DRIVE}/tools/osx/generated_DS_Store"
    local app_version

    build_extension
    echo ">>> [package] Adding the extension to the package"
    mkdir "${pkg_path}/Contents/PlugIns"
    mv -fv "${WORKSPACE_DRIVE}/NuxeoFinderSync.appex" "${pkg_path}/Contents/PlugIns/"

    if [ "${GITHUB_WORKSPACE:-unset}" != "unset" ]; then
        prepare_signing_from_scratch
    else
        prepare_signing
    fi

    if [ "${SIGNING_ID:-unset}" != "unset" ]; then
        echo ">>> [sign] Signing the app and its extension"
        # We recursively sign all the files
        # A message indicating "code object is not signed at all" can appear:
        # This is normal. The find command goes through the binaries in an
        # arbitrary order. When the `codesign` runs, it will look at some
        # dependencies of the current binary and see that they are not signed
        # yet. But the find command will eventually reach it and sign it later.
        find "${pkg_path}/Contents/MacOS" -type f -exec ${CODESIGN} "${SIGNING_ID}" {} \;

        # QML libraries need to be signed too for the notarization
        find "${pkg_path}/Contents/Resources" -type f -name "*.dylib" -exec ${CODESIGN} "${SIGNING_ID}" {} \;

        # Then we sign the extension
        ${CODESIGN} "${SIGNING_ID}"                  \
                    --force                          \
                    --deep                           \
                    --entitlements "${entitlements}" \
                    "${pkg_path}/Contents/PlugIns/NuxeoFinderSync.appex"

        # And we shallow sign the .app
        ${CODESIGN} "${SIGNING_ID}" "${pkg_path}"

        echo ">>> [sign] Verifying code signature"
        codesign --display --verbose "${pkg_path}"
        codesign --verbose=4 --deep --strict "${pkg_path}"
        spctl --assess --verbose "${pkg_path}"
    fi

    echo ">>> [package] Creating the DMG file"

    app_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
    local dmg_path="${output_dir}/nuxeo-drive-${app_version}.dmg"

    # Clean-up
    rm -fv "${dmg_path}"
    rm -rf "${src_folder_tmp}" "${dmg_tmp}"
    mkdir "${src_folder_tmp}"

    echo ">>> [DMG] ${bundle_name} version ${app_version}"
    # Compute DMG name and size
    local dmg_size=$(( $(du -sm "${pkg_path}" | cut -d$'\t' -f1,1) + 20 ))
    echo ">>> [DMG ${app_version}] ${dmg_path} (${dmg_size} Mo)"

    echo ">>> [DMG ${app_version}] Preparing the DMG"
    cp -a "${pkg_path}" "${src_folder_tmp}"
    mkdir "${src_folder_tmp}/.background"
    cp "${background_file}" "${src_folder_tmp}/.background"
    cp "${generated_ds_store}" "${src_folder_tmp}/.DS_Store"
    ln -s /Applications "${src_folder_tmp}"

    echo ">>> [DMG ${app_version}] Creating the DMG"
    hdiutil create                         \
            -srcfolder "${src_folder_tmp}" \
            -volname "${app_name}"         \
            -fs HFS+                       \
            -fsargs "-c c=64,a=16,e=16"    \
            -format UDRW                   \
            -size "${dmg_size}m"           \
            "${dmg_tmp}"

    rm -f "${dmg_path}"
    hdiutil convert "${dmg_tmp}" \
            -format UDZO         \
            -imagekey            \
            zlib-level=9         \
            -o "${dmg_path}"

    # Clean tmp directories
    rm -rf "${src_folder_tmp}" "${dmg_tmp}" "${pkg_path}"

    if [ "${SIGNING_ID:-unset}" != "unset" ]; then
        ${CODESIGN} "${SIGNING_ID}" --verbose "dist/nuxeo-drive-${app_version}.dmg"
        ${PYTHON} tools/osx/notarize.py "dist/nuxeo-drive-${app_version}.dmg"
    fi
}

main "$@"
