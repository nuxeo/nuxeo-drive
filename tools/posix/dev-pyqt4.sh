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
source ../python_version

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

    pip install -r "../../requirements.txt"
    pip install -r "../../unix-requirements.txt"
    if is_mac; then
        pip install -r "../../mac-requirements.txt"
    fi
}

is_mac() {
    if [ `uname -a|awk '{print $1}'` = "Darwin" ]; then
        return 0
    fi
    return 1
}

install_sip_linux() {
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

install_pyqt4_darwin() {
    brew install qt
    brew install pyqt
}

install_pyqt4_linux() {
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
    verify_python
    # Check PyQt4.QtWebKit installation inside its virtualenv
    setup_venv --no-install
    check_qtwebkit
}

remove_tmp() {
    # Delete downloaded files and extracted folders on successful installation
    rm -rf PyQt4_gpl_x11-4.12* sip-4.19*
}

commands_exists() {
    type $1 >/dev/null 2>&1 || { return 1; }
}

verify_python() {
    if ! commands_exists "python"; then
        echo >&2 "Requires Python $PYTHON_DRIVE_VERSION.  Aborting.";
        exit 1;
    fi

    CUR_VERSION=`python --version 2>&1 |awk '{print $2}'`
    if [ "$CUR_VERSION" != "$PYTHON_DRIVE_VERSION" ]; then
        echo "Python version is $CUR_VERSION"
        echo "Drive requires Python version $PYTHON_DRIVE_VERSION"
        exit 1
    fi
}

main() {
    # Launch operations
    [ $# -eq 1 ] && \
        VENV="$1"

    check_install && \
        return

    setup_venv
    if is_mac; then
        install_pyqt4_darwin
    else
        install_sip_linux
        install_pyqt4_linux
    fi
    check_qtwebkit && \
        remove_tmp
}

main "$@"
