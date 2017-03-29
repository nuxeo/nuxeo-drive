#!/bin/sh -eu
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

export OSI="osx"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/osx/', '/posix/'))")"

create_package() {
    # Create the final DMG
    local app_name="Nuxeo Drive"
    local bundle_name="$app_name.app"
    local output_dir="${WORKSPACE_DRIVE}/dist"
    local pkg_path="${output_dir}/${bundle_name}"
    local src_folder_tmp="${WORKSPACE}/dmg_src_folder.tmp"
    local dmg_tmp="${WORKSPACE}/nuxeo-drive.tmp.dmg"
    local background_file="${WORKSPACE_DRIVE}/tools/osx/dmgbackground.png"
    local generated_ds_store="${WORKSPACE_DRIVE}/tools/osx/generated_DS_Store"
    local signing_id="NUXEO CORP"
    local update_pkg_name=$(ls "${output_dir}" | grep "${app_name}")

    # Rename frozen app to have a normalized DMG name
    [ -d "${pkg_path}" ] && rm -rf "${pkg_path}"
    mv "${output_dir}/${app_name}"* "${pkg_path}"

    local app_version="$("${pkg_path}/Contents/MacOS/ndrive" -v 2>&1)"
    echo ">>> [DMG] ${bundle_name} version ${app_version}"

    # Compute DMG name and size
    local dmg_path="${output_dir}/nuxeo-drive-${app_version}-osx.dmg"
    local dmg_size=$(( $(du -sm "${pkg_path}" | cut -d$'\t' -f1,1) + 20 ))
    echo ">>> [DMG ${app_version}] ${dmg_path} (${dmg_size} Mo)"

    # Fix to prevent conflicts if there are several Qt installations on the system
    # Source: http://stackoverflow.com/a/11071241
    local esky_app_name="${app_name}-${app_version}.$(python -c "import esky.util; print(esky.util.get_platform())")"
    echo ">>> [DMG ${app_version}] Fixing Qt choice"
    touch "${pkg_path}/appdata/${esky_app_name}/${bundle_name}/Contents/Resources/qt.conf"

    # TODO: reactivate with new certificate
    # TODO: add parameters to Jenkinsfile
    #echo ">>> Unlocking the Nuxeo keychain"
    #security unlock-keychain -p "${NUXEO_KEYCHAIN_PWD}" "${NUXEO_KEYCHAIN_PATH}"

    #echo ">>> [DMG ${app_version}] Signing the app bundle"
    #codesign -s "${signing_id}" "${pkg_path}"

    #echo ">>> [DMG ${app_version}] Verifying code signature"
    #codesign "{$pkg_path}"
    #codesign -d "${pkg_path}"
    #spctl --assess --type execute "${pkg_path}"

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

    echo ">>> [DMG ${app_version}] Zipping application bundle to make it available as an update"
    zip -r "${output_dir}/${update_pkg_name}.zip" "${pkg_path}"
}

fix_version() {
    # Fix for Esky that cannot update between different macOS versions.
    # For instance, even if macOS 10.12 is compatible with 10.4, a package
    # created with 10.12 cannot be updated with the 10.4 version.
    #
    # Example with these releases:
    #     Nuxeo Drive-2.1.0914.macosx-10_10-x86_64.zip
    #     Nuxeo Drive-2.1.1130.macosx-10_12-x86_64.zip
    #     Nuxeo Drive-2.1.1221.macosx-10_10-x86_64.zip
    #
    # You will       be able to update from 2.1.0914 to 2.1.1221.
    # You will _not_ be able to update from 2.1.0914 to 2.1.1130.
    # You will _not_ be able to update from 2.1.1130 to 2.1.1221.
    #
    # So, we use "universal" builds by setting the version to the minimal, i.e. 10.4.
    #
    # See distutils/utils.py get_platform() for technical details about how Esky
    # build the version for the current OS.
    export _PYTHON_HOST_PLATFORM="${_PYTHON_HOST_PLATFORM:=macosx-10_4-x86_64}"
}

unfix_version() {
    unset _PYTHON_HOST_PLATFORM
}

main "$@"
