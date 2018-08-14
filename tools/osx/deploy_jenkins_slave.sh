#!/bin/sh -eu
# See tools/posix/deploy_jenkins_slave.sh for more information and arguments.

export OSI="osx"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/osx/', '/posix/'))")"

prepare_signing() {
    # Code sign the app
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-OSX-Code-Signing

    if [ "${SIGNING_ID:=unset}" = "unset" ]; then
        echo ">>> [sign] WARNING: Signing ID is unavailable, application won't be signed."
        return
    elif [ "${LOGIN_KEYCHAIN_PASSWORD:=unset}" = "unset" ]; then
        echo ">>> [sign] WARNING: Keychain is unavailable, application won't be signed."
        return
    fi

    echo ">>> [sign] Unlocking the Nuxeo keychain"
    security unlock-keychain -p "${LOGIN_KEYCHAIN_PASSWORD}" "${LOGIN_KEYCHAIN_PATH}"
    # set-key-partition-list was added in Sierra (macOS 10.12)
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "${LOGIN_KEYCHAIN_PASSWORD}" "${LOGIN_KEYCHAIN_PATH}" || true
    security set-keychain-settings "${LOGIN_KEYCHAIN_PATH}"
}

build_extension() {
    # Create the FinderSync extension, if not already done
    local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive"

    if test -f "${WORKSPACE_DRIVE}/extension.zip"; then
        # The extension has been unstashed from a specific job, just decompress it
        echo ">>> [package] Decompressing the FinderSync extension"
        unzip -o -d "${WORKSPACE_DRIVE}" "${WORKSPACE_DRIVE}/extension.zip"
        rm -fv "${WORKSPACE_DRIVE}/extension.zip"
        return
    fi

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
    local generated_ds_store="${WORKSPACE_DRIVE}/tools/osx/generated_DS_Store"
    local app_version="$(python "${WORKSPACE_DRIVE}/tools/changelog.py" --drive-version)"

    build_extension
    echo ">>> [package] Adding the extension to the package"
    mkdir "${pkg_path}/Contents/PlugIns"
    mv -fv "${WORKSPACE_DRIVE}/NuxeoFinderSync.appex" "${pkg_path}/Contents/PlugIns/."

    echo ">>> [package] Creating the DMG file"
    rm -fv ${output_dir}/*.dmg

    prepare_signing
    if [ "${SIGNING_ID:=unset}" != "unset" ]; then
        echo ">>> [sign] Signing the app extension"
        codesign -dfvs "${SIGNING_ID}" --entitlements "${extension_path}/NuxeoFinderSync/NuxeoFinderSync.entitlements" "${pkg_path}/Contents/PlugIns/NuxeoFinderSync.appex"

        echo ">>> [sign] Signing the app"
        # We sign the files without --force so the app
        # extension keeps its entitlements and its sandboxing
        codesign -vs "${SIGNING_ID}" "${pkg_path}"

        echo ">>> [sign] Verifying code signature"
        codesign -vv "${pkg_path}"
        spctl --assess -vv "${pkg_path}"
    fi

    echo ">>> [DMG] ${bundle_name} version ${app_version}"
    # Compute DMG name and size
    local dmg_path="${output_dir}/nuxeo-drive-${app_version}.dmg"
    local dmg_size=$(( $(du -sm "${pkg_path}" | cut -d$'\t' -f1,1) + 20 ))
    echo ">>> [DMG ${app_version}] ${dmg_path} (${dmg_size} Mo)"

    # Clean tmp directories
    rm -rf "${src_folder_tmp}" "${dmg_tmp}"
    mkdir "${src_folder_tmp}"

    echo ">>> [DMG ${app_version}] Preparing the DMG"
    cp -a "${pkg_path}" "${src_folder_tmp}"
    mkdir "${src_folder_tmp}/.background"
    cp "${background_file}" "${src_folder_tmp}/.background"
    cp "${generated_ds_store}" "${src_folder_tmp}/.DS_Store"
    ln -s /Applications "${src_folder_tmp}"

    echo ">>> [DMG ${app_version}] Creating the DMG"
    hdiutil create -srcfolder "${src_folder_tmp}" -volname "${app_name}" -fs HFS+ -fsargs "-c c=64,a=16,e=16" -format UDRW -size "${dmg_size}m" "${dmg_tmp}"

    rm -f "$dmg_path}"
    hdiutil convert "${dmg_tmp}" -format UDZO -imagekey zlib-level=9 -o "${dmg_path}"

    # Clean tmp directories
    rm -rf "${src_folder_tmp}" "${dmg_tmp}"

    if [ "${SIGNING_ID:=unset}" != "unset" ]; then
        codesign -vs "${SIGNING_ID}" "dist/nuxeo-drive-${app_version}.dmg"
    fi
    rm -rf "${pkg_path}"
}

main "$@"
