#!/bin/sh
#
# 2017-01-18 Mickaël Schoentgen, Nuxeo SAS
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
# You will need these too (you can delete it after a successful installation):
#
#    $ sudo apt install qt4-qmake libqt4-dev libqtwebkit-dev
#
### Usage
#
#    $ chmod +x dev-pyqt4.sh
#    $ ./dev-pyqt4.sh [DEST_DIR]
#
# Default virtualenv directory: $HOME/drive-venv
# You can override this parameter by setting DEST_DIR.
#

set -eu

# Global variable of the virtualenv ath installation
VENV="$HOME/drive-venv"


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
        tar zxf "$file"
}

setup_venv() {
    # Setup virtualenv
    local action="--install"
    [ "$#" -eq 1 ] && \
        action="--no-install"

    echo ">>> Setting up the virtualenv into $VENV"

    [ -d "$VENV" ] || \
        virtualenv \
            -p /usr/bin/python2.7 \
            --no-site-packages \
            --always-copy \
            "$VENV"

    . "${VENV}/bin/activate"

    # A simple use of the virtualenv for tests, no install required
    [ "$action" = "--no-install" ] && \
        return

    pip install -r "requirements.txt"
    pip install -r "unix-requirements.txt"
}

install_sip() {
    # Install SIP
    local url="https://sourceforge.net/projects/pyqt/files/sip/sip-4.19/sip-4.19.tar.gz"
    local path="sip-4.19"
    local output="${path}.tar.gz"

    echo ">>> Installing SIP"

    download "$url" "$output"
    extract "$output" "$path"

    cd "$path"
    python configure.py
    make
    make install
    cd ..
}

install_pyqt4() {
    # Install PyQt4 + QtWebKit
    local url="http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.12/PyQt4_gpl_x11-4.12.tar.gz"
    local path="PyQt4_gpl_x11-4.12"
    local output="${path}.tar.gz"

    echo ">>> Installing PyQt4 with WebKit support"

    download "$url" "$output"
    extract "$output" "$path"

    cd "$path"
    python configure-ng.py \
        --confirm-license \
        --concatenate
    make
    make install
    cd ..
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
    setup_venv --no-install
    check_qtwebkit
}

remove_tmp() {
    # Delete downloaded files and extracted folders on successful installation
    rm -rf PyQt4_gpl_x11-4.12* sip-4.19*
}

main() {
    # Launch operations
    [ $# -eq 1 ] && \
        VENV="$1"

    check_install && \
        return

    setup_venv
    install_sip
    install_pyqt4
    check_qtwebkit && \
        remove_tmp
}

main "$@"
