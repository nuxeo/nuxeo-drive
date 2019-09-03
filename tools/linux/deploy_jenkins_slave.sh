#!/bin/bash
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

set -e

export OSI="linux"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"

remove_blacklisted_files() {
    # Remove blacklisted files known as having bad side effects
    local app_dir="$1"

    echo ">>> [${app_dir}] Removing blacklisted files"

    [ -f excludelist ] && rm -fv excludelist
    wget "https://raw.githubusercontent.com/AppImage/pkg2appimage/master/excludelist"

    while IFS= read -r line; do
        file="$(echo "${line}" | cut -d' ' -f1)"
        if [ ! "${file}" = "" ] && [ ! "${file}" = "#" ]; then
            [ -f "${app_dir}/${file}" ] && rm -fv "${app_dir}/${file}"
        fi
    done < excludelist

    rm -fv excludelist
}

create_package() {
    # Create the final AppImage
    local app_name="nuxeo-drive"
    local app_id="org.nuxeo.drive"
    local app_version="$(python tools/changelog.py --drive-version)"
    local app_dir="dist/AppRun"

    echo ">>> [AppImage] Adjusting file names to fit in the AppImage"
    # Taken from https://gitlab.com/scottywz/ezpyi/blob/master/ezpyi
    [ -d "${app_dir}" ] && rm -rfv "${app_dir}"
    mv -v "dist/ndrive" "${app_dir}"
    mv -v "${app_dir}/ndrive" "${app_dir}/AppRun"

    echo ">>> [AppImage] Copying icons"
    cp -v "tools/linux/app_icon.svg" "${app_dir}/.DirIcon.svg"
    cp -v "tools/linux/app_icon.svg" "${app_dir}/.icon.svg"

    echo ">>> [AppImage] Copying metadata files"
    mkdir -pv "${app_dir}/usr/share/metainfo"
    cp -v "tools/linux/${app_id}.appdata.xml" "${app_dir}/usr/share/metainfo"
    mkdir -pv "${app_dir}/usr/share/applications"
    cp -v "tools/linux/${app_id}.desktop" "${app_dir}/usr/share/applications"
    ln -srv "${app_dir}/usr/share/applications/${app_id}.desktop" "${app_dir}/${app_id}.desktop"

    echo ">>> [AppImage] Downloading the AppImage tool"
    [ -f "appimagetool-x86_64.AppImage" ] && rm -fv "appimagetool-x86_64.AppImage"
    [ -d "squashfs-root" ] && rm -frv "squashfs-root"
    wget "https://github.com/AppImage/AppImageKit/releases/download/12/appimagetool-x86_64.AppImage"
    chmod -v a+x "appimagetool-x86_64.AppImage"
    ./appimagetool-x86_64.AppImage --appimage-extract

    echo ">>> [AppImage] Creating the AppImage file"
    # --no-appstream because appstreamcli is not easily installable on CentOS
    ./squashfs-root/AppRun --no-appstream "${app_dir}" "dist/${app_name}-${app_version}-x86_64.AppImage"

    echo ">>> [AppImage] Downloading AppImage conformity tools"
    [ -f "excludelist" ] && rm -fv "excludelist"
    [ -f "appdir-lint.sh" ] && rm -fv "appdir-lint.sh"
    wget "https://github.com/AppImage/pkg2appimage/raw/master/excludelist"
    wget "https://github.com/AppImage/pkg2appimage/raw/master/appdir-lint.sh"

    echo ">>> [AppImage] Checking the AppImage conformity"
    bash appdir-lint.sh "${app_dir}"
    appstream-util validate-relax "${app_dir}/usr/share/metainfo/${app_id}.appdata.xml"
    echo "!!! Further checks needed, not usable on CentOS, keep it as example and regularly do it manually"
    echo "appstreamcli validate '${app_dir}/usr/share/metainfo/${app_id}.appdata.xml'"
    echo "appstreamcli validate-tree '${app_dir}'"

    echo ">>> [AppImage] Clean-up"
    [ -f "appimagetool-x86_64.AppImage" ] && rm -fv "appimagetool-x86_64.AppImage"
    [ -d "squashfs-root" ] && rm -frv "squashfs-root"
    [ -f "excludelist" ] && rm -fv "excludelist"
    [ -f "appdir-lint.sh" ] && rm -fv "appdir-lint.sh"
}

main "$@"
