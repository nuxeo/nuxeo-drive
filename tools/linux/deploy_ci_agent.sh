#!/bin/bash
# See tools/posix/deploy_ci_agent.sh for more information and arguments.

set -e

export OSI="linux"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"

remove_excluded_files() {
    # Remove denylisted files known as having bad side effects
    local app_dir="$1"

    echo ">>> [${app_dir}] Removing excluded files"
    while IFS= read -r line; do
        file="$(echo "${line}" | cut -d' ' -f1)"
        if [ ! "${file}" = "" ] && [ ! "${file}" = "#" ]; then
            [ -f "${app_dir}/${file}" ] && rm -fv "${app_dir}/${file}"
        fi
    done < tools/linux/appimage/excludelist

    return 0  # <-- Needed, do not remove!
}

check() {
    # Check AppImage conformity.
    echo ">>> [AppImage] Extracting the AppImage"
    cd dist
    [ -f "squashfs-root" ] && rm -rf "squashfs-root"
    ./*-x86_64.AppImage --appimage-extract
    cd ..

    echo ">>> [AppImage] Checking the version"
    ./dist/squashfs-root/AppRun --version

    echo ">>> [AppImage] Checking the AppImage conformity"
    ./tools/linux/appimage/appdir-lint.sh "$(pwd)/dist/squashfs-root"

    echo ">>> [AppImage] Clean-up"
    rm -rf dist/squashfs-root

    return 0  # <-- Needed, do not remove!
}

find_appimage() {
    # Find the AppImage in the dist folder
    shopt -s nullglob
    appimage_files=(dist/*-x86_64.AppImage)
    shopt -u nullglob

    if [ ${#appimage_files[@]} -eq 0 ]; then
        echo ">>> [AppImage] No AppImage found in the dist folder"
        exit 1
    elif [ ${#appimage_files[@]} -gt 1 ]; then
        echo ">>> [AppImage] Multiple AppImages found in the dist folder:"
        for f in "${appimage_files[@]}"; do
            echo "    $f"
        done
        echo ">>> [AppImage] Aborting to prevent signing the wrong file."
        exit 1
    fi

    appimage_file="${appimage_files[0]}"
}

sign() {
    # Import GPG Private Key for signing the AppImage
    if [ -n "$GPG_PRIVATE_KEY" ]; then
        echo "$GPG_PRIVATE_KEY" | gpg --batch --import
        if [ $? -ne 0 ]; then
            echo ">>> [AppImage] Failed to import GPG private key"
            exit 1
        fi
    fi

    # Check if GPG_PASSPHRASE is set
    if [ -z "$GPG_PASSPHRASE" ]; then
        echo ">>> [AppImage] GPG_PASSPHRASE is not set"
        exit 1
    fi

    find_appimage

    # Sign the AppImage with a detached signature
    gpg --batch --yes --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" --output "${appimage_file}.sig" --detach-sign "$appimage_file"

    echo ">>> [AppImage] AppImage signed: ${appimage_file}.sig"
    return 0  # <-- Needed, do not remove!
}

verify_sign() {
    GPG_KEY_FPR="E660E4095687C2F71F5938D616D39950F9D3F3DF"

    # Import GPG Public Key from keyserver
    echo ">>> [AppImage] Importing GPG public key with ID: $GPG_KEY_FPR from keys.openpgp.org"
    gpg --keyserver hkps://keys.openpgp.org --recv-keys "$GPG_KEY_FPR"
    if [ $? -ne 0 ]; then
        echo ">>> [AppImage] Failed to import GPG public key"
        exit 1
    fi

    # Set trust level to ultimate
    echo "$GPG_KEY_FPR:6:" | gpg --batch --yes --import-ownertrust

    find_appimage

    # Verify the signature
    gpg --verify "${appimage_file}.sig" "$appimage_file"
    if [ $? -eq 0 ]; then
        echo ">>> [AppImage] Signature verification successful"
    else
        echo ">>> [AppImage] Signature verification failed"
        exit 1
    fi
}

create_package() {
    # Create the final AppImage
    local app_name="nuxeo-drive"
    local app_id="org.nuxeo.drive"
    local app_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
    local app_dir="dist/AppRun"
    local output="dist/${app_name}-${app_version}-x86_64.AppImage"

    echo ">>> [AppImage ${app_version}] Adjusting file names to fit in the AppImage"
    # Taken from https://gitlab.com/scottywz/ezpyi/blob/master/ezpyi
    [ -d "${app_dir}" ] && rm -rf "${app_dir}"
    mv -v "dist/ndrive" "${app_dir}"
    mv -v "${app_dir}/ndrive" "${app_dir}/AppRun"

    echo ">>> [AppImage ${app_version}] Copying icons"
    cp -v "tools/linux/DirIcon.png" "${app_dir}/.DirIcon"
    cp -v "nxdrive/data/icons/app_icon.svg" "${app_dir}/${app_name}.svg"

    echo ">>> [AppImage ${app_version}] Copying metadata files"
    mkdir -pv "${app_dir}/usr/share/metainfo"
    cp -v "tools/linux/${app_id}.appdata.xml" "${app_dir}/usr/share/metainfo"
    mkdir -pv "${app_dir}/usr/share/applications"
    cp -v "tools/linux/${app_id}.desktop" "${app_dir}/usr/share/applications"
    ln -srv "${app_dir}/usr/share/applications/${app_id}.desktop" "${app_dir}/${app_id}.desktop"

    more_compatibility

    echo ">>> [AppImage] Decompressing the AppImage tool"
    cd build
    [ -d "squashfs-root" ] && rm -frv "squashfs-root"
    ./../tools/linux/appimage/appimagetool-x86_64.AppImage --appimage-extract
    cd ..

    echo ">>> [AppImage ${app_version}] Creating the AppImage file"
    # --no-appstream because appstreamcli is not easily installable on CentOS
    ./build/squashfs-root/AppRun --no-appstream "${app_dir}" "${output}"

    echo ">>> [AppImage] Clean-up"
    rm -rf squashfs-root

    return 0  # <-- Needed, do not remove!
}

more_compatibility() {
    echo ">>> [AppImage ${app_version}] Adding more files to expand compatibility"

    # Needed on Fedora 30+ (see https://github.com/slic3r/Slic3r/issues/4798)
    cp -v /usr/lib64/libcrypt-2.17.so "${app_dir}/libcrypt.so.1" || true

    return 0  # <-- Needed, do not remove!
}

main "$@"
