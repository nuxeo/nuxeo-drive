#!/bin/bash
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

set -e

export OSI="linux"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"

remove_blacklisted_files() {
    # Remove blacklisted files known as having bad side effects
    local appdir="$1"

    echo ">>> [${appdir}] Removing blacklisted files"

    [ -f excludelist ] && rm -fv excludelist
    wget "https://raw.githubusercontent.com/AppImage/pkg2appimage/master/excludelist"

    while IFS= read -r line; do
        file="$(echo "${line}" | cut -d' ' -f1)"
        if [ ! "${file}" = "" ] && [ ! "${file}" = "#" ]; then
            [ -f "${appdir}/${file}" ] && rm -fv "${appdir}/${file}"
        fi
    done < excludelist

    rm -fv excludelist
}

create_package() {
    # Create the final AppImage
    local app_name="nuxeo-drive"
    local app_version="$(python tools/changelog.py --drive-version)"
    local appdir="dist/AppRun"

    echo ">>> [AppImage] Adjusting file names to fit in the AppImage"
    # Taken from https://gitlab.com/scottywz/ezpyi/blob/master/ezpyi
    [ -d "${appdir}" ] && rm -rfv "${appdir}"
    mv -v dist/ndrive "${appdir}"
    mv -v "${appdir}/ndrive" "${appdir}/AppRun"

    echo ">>> [AppImage] Copying metadata files"
    cp -v tools/linux/app.desktop "${appdir}/.desktop"
    cp -v tools/linux/app_icon.svg "${appdir}/.DirIcon.svg"
    cp -v tools/linux/app_icon.svg "${appdir}/.icon.svg"

    echo ">>> [AppImage] Downloading the AppImage tool"
    wget https://github.com/AppImage/AppImageKit/releases/download/12/appimagetool-x86_64.AppImage
    chmod a+x appimagetool-x86_64.AppImage
    ./appimagetool-x86_64.AppImage --appimage-extract

    echo ">>> [AppImage] Creating the AppImage file"
    ./squashfs-root/AppRun --no-appstream "${appdir}" "dist/${app_name}-${app_version}-x86_64.AppImage"
}

main "$@"
