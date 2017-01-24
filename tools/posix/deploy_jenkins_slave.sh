#!/bin/sh -eu
# Shared functions for tools/$OSI/deploy_jenkins_slave.sh files.
#
# Usage: sh tools/$OSI/deploy_jenkins_slave.sh [ARG]
#
# Possible ARG:
#     --build: build the package
#     --tests: launch the tests suite
#
# Dependencies: https://github.com/yyuu/pyenv/wiki/Common-build-problems#requirements
#
### About environment variables
#
# PYTHON_DRIVE_VERSION is the required Python version to use, i.e. "2.7.13".
# PYQT_VERSION is the required PyQt version to use, i.e. "4.12".
# WORKSPACE is the absolute path to the WORKSPACE, i.e. "/opt/jenkins/workspace/xxx"
#
#### Optional envvars
#
# WORKSPACE_DRIVE is the absolute path to Drive sources, i.e. "$WORKSPACE/sources".
#     If not defined, it will be set to $WORKSPACE/sources or $WORKSPACE/nuxeo-drive if found else $WORKSPACE.
# SIP_VERSION is the SIP version to use, i.e. "4.19".
#

#set -x  # verbose

# Global variables
PIP="pip install -q --upgrade"

build_esky() {
    echo ">>> Building the release package"
    python setup.py bdist_esky

    case "${OSI}" in
        "linux")
            echo ">>> [package] Creating the DEB file"
            echo ">>> [package] TODO The DEB creation for GNU/Linux is not yet implemented."
            # create_package
            ;;
        "osx")
            echo ">>> [package] Creating the DMG file"
            create_package
            ;;
    esac
}

check_import() {
    # Check module import to know if it must be installed
    # i.e: check_import "from PyQt4 import QtWebKit"
    #  or: check_import "import cx_Freeze"
    local import="$1"
    local ret=0

    /bin/echo -n ">>> Checking module: ${import} ... "
    python -c "${import}" 2>/dev/null || ret=1
    if [ ${ret} -ne 0 ]; then
        echo "Failed."
        return 1
    fi
    echo "OK."
}

check_vars() {
    # Check required variables
    if [ "${PYTHON_DRIVE_VERSION:=unset}" = "unset" ]; then
        echo "PYTHON_DRIVE_VERSION not defined. Aborting."
        exit 1
    elif [ "${PYQT_VERSION:=unset}" = "unset" ]; then
        echo "PYQT_VERSION not defined. Aborting."
        exit 1
    elif [ "${WORKSPACE:=unset}" = "unset" ]; then
        echo "WORKSPACE not defined. Aborting."
        exit 1
    elif [ "${OSI:=unset}" = "unset" ]; then
        echo "OSI not defined. Aborting."
        echo "Please do not call this script directly. Use the good one from 'tools/OS/deploy_jenkins_slave.sh'."
        exit 1
    fi
    export STORAGE_DIR="${WORKSPACE}/deploy-dir"

    # Check optional variables
    if [ "${WORKSPACE_DRIVE:=unset}" = "unset" ]; then
        if [ -d "${WORKSPACE}/sources" ]; then
            export WORKSPACE_DRIVE="${WORKSPACE}/sources"
        elif [ -d "${WORKSPACE}/nuxeo-drive" ]; then
            export WORKSPACE_DRIVE="${WORKSPACE}/nuxeo-drive"
        else
            export WORKSPACE_DRIVE="${WORKSPACE}"
        fi
    fi
    cd "${WORKSPACE_DRIVE}"

    echo "    PYTHON_DRIVE_VERSION = ${PYTHON_DRIVE_VERSION}"
    echo "    PYQT_VERSION         = ${PYQT_VERSION}"
    echo "    WORKSPACE            = ${WORKSPACE}"
    echo "    WORKSPACE_DRIVE      = ${WORKSPACE_DRIVE}"
    echo "    STORAGE_DIR          = ${STORAGE_DIR}"
}

download() {
    # Download one file and save its content to a given file name
    local url="$1"
    local output="$2"

    echo ">>> Downloading $url"
    echo "             to $output"
    [ -f "$output" ] || curl --silent -L "$url" > "$output"
}

extract() {
    # Extract a downloaded file
    local file="$1"
    local folder="$2"

    echo ">>> Extracting $file"
    echo "            to $folder"
    [ -d "$folder" ] || tar zxf "$file" -C "${STORAGE_DIR}"
}

install_deps() {
    echo ">>> Installing requirements"
    ${PIP} -r requirements.txt
    ${PIP} -r requirements-unix.txt
    case "${OSI}" in
        "osx") ${PIP} -r requirements-mac.txt ;;
    esac
}

install_pyenv() {
    local url="https://raw.githubusercontent.com/yyuu/pyenv-installer/master/bin/pyenv-installer"

    echo ">>> [pyenv] Setting up"
    export PYENV_ROOT="${STORAGE_DIR}/.pyenv"
    export PATH="${PYENV_ROOT}/bin:$PATH"

    if ! hash pyenv 2>/dev/null; then
        echo ">>> [pyenv] Downloading and installing"
        curl --silent -L "${url}" | bash
    fi

    echo ">>> [pyenv] Initializing"
    eval "$(pyenv init -)"
    eval "$(pyenv virtualenv-init -)"
}

install_pyqt() {
    local version="$1"
    local url="https://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-${version}"
    local path="${STORAGE_DIR}"
    case "${OSI}" in
        "linux")
            url="${url}/PyQt4_gpl_x11-${version}.tar.gz"
            path="${path}/PyQt4_gpl_x11-${version}"
            ;;
        "osx")
            url="${url}/PyQt4_gpl_mac-${version}.tar.gz"
            path="${path}/PyQt4_gpl_mac-${version}"
            ;;
    esac
    local output="${path}.tar.gz"

    # First, we need to install SIP
    install_sip

    check_import "import PyQt4.QtWebKit" && return
    echo ">>> Installing PyQt ${version}"

    download "$url" "$output"
    extract "$output" "$path"

    cd "$path"

    echo ">>> [PyQt ${version}] Configuring"
    python configure-ng.py \
        --confirm-license \
        --no-designer-plugin \
        --no-docstrings \
        --no-python-dbus \
        --no-qsci-api \
        --no-tools

    echo ">>> [PyQt ${version}] Compiling"
    make --quiet -j 4

    echo ">>> [PyQt ${version}] Installing"
    make --quiet install

    cd "${WORKSPACE_DRIVE}"
}

install_python() {
    local version="$1"

    install_pyenv

    # To fix Mac error when building the package "libpython27.dylib does not exist"
    [ "${OSI}" = "osx" ] && export PYTHON_CONFIGURE_OPTS="--enable-shared"

    pyenv install --skip-existing "${version}"

    echo ">>> [pyenv] Using Python ${version}"
    pyenv global "${version}"
}

install_sip() {
    local version="${SIP_VERSION:=4.19}"
    local url="https://sourceforge.net/projects/pyqt/files/sip/sip-${version}/sip-${version}.tar.gz"
    local path="${STORAGE_DIR}/sip-${version}"
    local output="${path}.tar.gz"

    check_import "import sipconfig" && return
    echo ">>> Installing SIP ${version}"

    download "$url" "$output"
    extract "$output" "$path"

    cd "$path"

    echo ">>> [SIP ${version}] Configuring"
    python configure.py

    echo ">>> [SIP ${version}] Compiling"
    make --quiet -j 4

    echo ">>> [SIP ${version}] Installing"
    make --quiet install

    cd "${WORKSPACE_DRIVE}"
}

launch_tests() {
    echo ">>> Launching the tests suite"

    ${PIP} -r requirements-tests.txt
    pytest nuxeo-drive-client/nxdrive \
        --showlocals \
        --exitfirst \
        --strict \
        --failed-first \
        -r Efx \
        --full-trace \
        --cache-clear \
        --capture=sys \
        --no-cov-on-fail \
        --cov-report html:../coverage \
        --cov=nuxeo-drive-client/nxdrive
}

verify_python() {
    local version="$1"
    local cur_version=$(python --version 2>&1 | awk '{print $2}')

    echo ">>> Verifying Python version in use"

    if [ "${cur_version}" != "${version}" ]; then
        echo "Python version ${cur_version}"
        echo "Drive requires ${version}"
        exit 1
    fi
}

# The main function, last in the script
main() {
    # Adjust PATH envar for Mac
    [ "${OSI}" = "osx" ] && export PATH="$PATH:/usr/local/bin"

    # Launch operations
    check_vars
    install_python "${PYTHON_DRIVE_VERSION}"
    verify_python "${PYTHON_DRIVE_VERSION}"
    install_pyqt "${PYQT_VERSION}"
    install_deps
    if ! check_import "import PyQt4.QtWebKit" > /dev/null; then
        echo ">>> Installation failed."
        exit 1
    fi

    if [ $# -eq 1 ]; then
        case "$1" in
            "--build") build_esky ;;
            "--tests") launch_tests ;;
        esac
    fi
}
