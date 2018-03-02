#!/bin/sh -eu
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

export OSI="osx"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/osx/', '/posix/'))")"

code_sign() {
    # Code sign the app
    # TODO: add parameters to Jenkinsfile
    # https://github.com/pyinstaller/pyinstaller/wiki/Recipe-OSX-Code-Signing
    local app="$1"

    if [[ -z ${SIGNING_ID:-} ]]; then
        echo ">>> [sign] WARNING: Signing ID is unavailable, application won't be signed."
        return
    elif [[ -z ${KEYCHAIN_PWD:-} ]]; then
        echo ">>> [sign] WARNING: Keychain is unavailable, application won't be signed."
        return
    fi

    echo ">>> [sign] Unlocking the Nuxeo keychain"
    security unlock-keychain -p "${KEYCHAIN_PWD}" "${KEYCHAIN_PATH}"

    echo ">>> [sign] Signing the file ${app}"
    if [[ $# > 1 ]]; then
        codesign --deep --force --preserve-metadata=entitlements --verbose --sign "${SIGNING_ID}" --entitlements $2 "${app}"
    else
        codesign --deep --force --verbose --sign "${SIGNING_ID}" "${app}"
    fi


    echo ">>> [sign] Verifying code signature"
    codesign --verify --verbose "${app}"
}

create_package() {
    # Create the final DMG
    local app_name="Nuxeo Drive"
    local bundle_name="Nuxeo Drive.app"
    local output_dir="${WORKSPACE_DRIVE}/dist"
    local pkg_path="${output_dir}/${bundle_name}"
    local src_folder_tmp="${WORKSPACE}/dmg_src_folder.tmp"
    local dmg_tmp="${WORKSPACE}/nuxeo-drive.tmp.dmg"
    local background_file="${WORKSPACE_DRIVE}/tools/osx/dmgbackground.png"
    local plist="${WORKSPACE_DRIVE}/tools/osx/Info.plist"
    local extension_path="${WORKSPACE_DRIVE}/tools/osx/drive"
    local generated_ds_store="${WORKSPACE_DRIVE}/tools/osx/generated_DS_Store"
    local app_version="$(python "${WORKSPACE_DRIVE}/tools/changelog.py" --drive-version)"

    echo ">>> [package] Updating Info.plist"
    sed "s/\$version/${app_version}/" "${plist}" > "${pkg_path}/Contents/Info.plist"

    echo ">>> [package] Building the FinderSync extension"
    xcodebuild -project "${extension_path}/drive.xcodeproj" -target "NuxeoFinderSync" -configuration Release build

    echo ">>> [package] Adding the extension to the package"
    mkdir "${pkg_path}/Contents/PlugIns"
    cp -a  "${extension_path}/build/Release/NuxeoFinderSync.appex" "${pkg_path}/Contents/PlugIns/."
    rm -rf "${extension_path}/build"

    echo ">>> [package] Creating the DMG file"
    code_sign "${pkg_path}/Contents/PlugIns/NuxeoFinderSync.appex" "${extension_path}/NuxeoFinderSync/NuxeoFinderSync.entitlements"
    code_sign "${pkg_path}" "${extension_path}/drive/drive.entitlements"

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

    code_sign "dist/nuxeo-drive-${app_version}.dmg"
    rm -rf "${pkg_path}"
}

main "$@"
