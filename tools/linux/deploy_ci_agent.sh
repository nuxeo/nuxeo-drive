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
    ./tools/linux/appimage/appdir-lint.sh "$(pwd)/tools/linux/appimage" "$(pwd)/dist/squashfs-root"

    echo ">>> [AppImage] Clean-up"
    rm -rf dist/squashfs-root

    return 0  # <-- Needed, do not remove!
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
