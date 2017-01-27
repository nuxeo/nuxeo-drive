#!/bin/sh
#
# Install PyQt4 with QtWebKit support into a virtualenv for Drive.
# If it succeeds, you will be able to launch Drive from that virtualenv.
#
# Note: keep in mind that we will drop Qt4 support for Qt5, this helper
#       script is for Drive developers/contributors or eventually users
#       using Debian based distributions with no more QtWebKit support.
#       source: https://wiki.debian.org/Qt4WebKitRemoval
#
### Dependencies
#
# You should have all binaries required for a full virtual environment
# using Python 2.7 and obvious system utilities like curl and tar.
#
# You will need these too (you can delete after a successful installation):
#
#    $ sudo apt install qt4-qmake libqt4-dev libqtwebkit-dev
#
### Usage
#
#    $ sh tools/posix/deploy_jenkins_slave.sh [ARGS]
#
# Possible ARGS:
#     --build: build the DMG package (MacOS X)
#

set -eu

# Global variables
[ -n "${WORKSPACE}" ] && \
    WORKSPACE="$(pwd)"
STORAGE_DIR="${WORKSPACE}/deploy-dir"
. tools/python_version
VENV="${STORAGE_DIR}/drive-$PYTHON_DRIVE_VERSION-venv"
PYTHON_INTERPRETER="$(which python)"

download() {
    # Download one file and save its content to a given file name
    local url="$1"
    local output="$2"

    echo ">>> Downloading $url to $output"

    [ -f "$output" ] || \
        curl -L "$url" > "$output"
}

extract() {
    # Extract a downloaded file
    local file="$1"
    local folder="$2"

    echo ">>> Extracting $file to $folder"

    [ -d "$folder" ] || \
        tar zxf "$file" -C "$STORAGE_DIR"
}

setup_venv() {
    # Setup virtualenv
    local action="--install"
    [ "$#" -eq 1 ] && \
        action="$1"

    echo ">>> Setting up the virtualenv into $VENV"

    [ -d "$VENV" ] || \
        virtualenv \
            -p ${PYTHON_INTERPRETER} \
            --system-site-packages \
            --always-copy \
            "$VENV"

    . "${VENV}/bin/activate"

    # A simple use of the virtualenv for tests, no install required
    [ "$action" = "--no-install" ] && \
        return

    pip install -r requirements.txt
    pip install -r unix-requirements.txt
    if is_mac; then
        pip install -r mac-requirements.txt
    fi
}

is_mac() {
    if [ `uname -a|awk '{print $1}'` = "Darwin" ]; then
        PYTHON_INTERPRETER="/usr/local/bin/python"
        return 0
    fi
    return 1
}

install_sip_linux() {
    # Install SIP
    local url="https://sourceforge.net/projects/pyqt/files/sip/sip-4.19/sip-4.19.tar.gz"
    local path="${STORAGE_DIR}/sip-4.19"
    local output="${path}.tar.gz"

    echo ">>> Installing SIP"

    download "$url" "$output"
    extract "$output" "$path"

    cd "$path"
    python configure.py
    make -j4
    make install
    cd "${WORKSPACE}"
}

install_pyqt4_darwin() {
    brew install qt
    brew install pyqt
}

install_pyqt4_linux() {
    # Install PyQt4 + QtWebKit
    local url="http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.12/PyQt4_gpl_x11-4.12.tar.gz"
    local path="${STORAGE_DIR}/PyQt4_gpl_x11-4.12"
    local output="${path}.tar.gz"

    echo ">>> Installing PyQt4 with WebKit support"

    download "$url" "$output"
    extract "$output" "$path"

    cd "$path"
    python configure-ng.py --confirm-license
    make -j4
    make install
    cd "${WORKSPACE}"
}

check_qtwebkit() {
    # Test if PyQt4.QtWebKit is installed and works
    python -c 'from PyQt4 import QtWebKit' && \
        echo ">>> Installation success!" && \
        return

    echo ">>> Installation failed."
    return 1
}

check_install() {
    # Check PyQt4.QtWebKit installation inside its virtualenv
    if is_mac; then
        verify_python
    fi
    setup_venv --no-install
    check_qtwebkit
}

remove_tmp() {
    # Delete downloaded files and extracted folders on successful installation
    rm -rf "${STORAGE_DIR}/PyQt4_gpl_x11-4.12*" "${STORAGE_DIR}/sip-4.19*"
}

commands_exists() {
    type $1 >/dev/null 2>&1 || return 1
}

verify_python() {
    if ! commands_exists "${PYTHON_INTERPRETER}"; then
        echo >&2 "Requires Python ${PYTHON_DRIVE_VERSION}.  Aborting.";
        exit 1;
    fi

    CUR_VERSION=`${PYTHON_INTERPRETER} --version 2>&1 |awk '{print $2}'`
    if [ "${CUR_VERSION}" != "${PYTHON_DRIVE_VERSION}" ]; then
        echo "Python version ${CUR_VERSION}"
        echo "Drive requires ${PYTHON_DRIVE_VERSION}"
        exit 1
    fi
}

build_esky() {
    # Build the famous DMG
    # TODO Make the DEB for GNU/Linux
    python setup.py bdist_esky
    if is_mac; then
        sh tools/osx/create-dmg.sh
    fi
}

main() {
    # Launch operations
    local build=0
    if [ $# -eq 1 ]; then
        if [ "$1" = "--build" ]; then
            build=1
        fi
    fi

    echo "    STORAGE_DIR = ${STORAGE_DIR}"
    echo "    VENV        = ${VENV}"

    if check_install; then
        if [ ${build} -eq 1 ]; then
            build_esky
        fi
        return
    fi

    setup_venv
    if is_mac; then
        install_pyqt4_darwin
    else
        install_sip_linux
        install_pyqt4_linux
    fi
    check_qtwebkit && \
        remove_tmp

    if [ ${build} -eq 1 ]; then
        build_esky
    fi
}

main "$@"
