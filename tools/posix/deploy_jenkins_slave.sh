#!/bin/sh -eu
# Shared functions for tools/$OSI/deploy_jenkins_slave.sh files.
#
# Usage: sh tools/$OSI/deploy_jenkins_slave.sh [ARG]
#
# Possible ARG:
#     --build: build the package
#     --build-ext: build the FinderSync extension (macOS only)
#     --start: start Nuxeo Drive
#     --tests: launch the tests suite
#
# See /docs/deployment.md for more information.
#

# Global variables
PYTHON="python -E -s"
PIP="${PYTHON} -m pip install --upgrade --upgrade-strategy=only-if-needed"

build_installer() {
    echo ">>> Building the release package"
    pyinstaller ndrive.spec --noconfirm
    create_package
}

check_import() {
    # Check module import to know if it must be installed
    # i.e: check_import "from PyQt4 import QtWebKit"
    #  or: check_import "import cx_Freeze"
    local import="$1"
    local ret=0

    /bin/echo -n ">>> Checking Python code: ${import} ... "
    ${PYTHON} -c "${import}" 2>/dev/null || ret=1
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
    elif [ "${WORKSPACE:=unset}" = "unset" ]; then
        echo "WORKSPACE not defined. Aborting."
        exit 1
    elif [ "${OSI:=unset}" = "unset" ]; then
        echo "OSI not defined. Aborting."
        echo "Please do not call this script directly. Use the good one from 'tools/OS/deploy_jenkins_slave.sh'."
        exit 1
    fi
    if [ "${WORKSPACE_DRIVE:=unset}" = "unset" ]; then
        if [ -d "${WORKSPACE}/sources" ]; then
            export WORKSPACE_DRIVE="${WORKSPACE}/sources"
        elif [ -d "${WORKSPACE}/nuxeo-drive" ]; then
            export WORKSPACE_DRIVE="${WORKSPACE}/nuxeo-drive"
        else
            export WORKSPACE_DRIVE="${WORKSPACE}"
        fi
    fi
    export STORAGE_DIR="${WORKSPACE}/deploy-dir"

    echo "    PYTHON_DRIVE_VERSION = ${PYTHON_DRIVE_VERSION}"
    echo "    WORKSPACE            = ${WORKSPACE}"
    echo "    WORKSPACE_DRIVE      = ${WORKSPACE_DRIVE}"
    echo "    STORAGE_DIR          = ${STORAGE_DIR}"

    cd "${WORKSPACE_DRIVE}"

    if [ "${SPECIFIC_TEST:=unset}" = "unset" ] ||
       [ "${SPECIFIC_TEST}" = "" ] ||
       [ "${SPECIFIC_TEST}" = "tests" ]; then
        export SPECIFIC_TEST="tests"
    else
        echo "    SPECIFIC_TEST        = ${SPECIFIC_TEST}"
        export SPECIFIC_TEST="tests/${SPECIFIC_TEST}"
    fi
}

install_deps() {
    echo ">>> Installing requirements"
    # Do not delete, it fixes "Could not import setuptools which is required to install from a source distribution."
    ${PIP} setuptools
    ${PIP} pip
    ${PIP} -r requirements.txt
    ${PIP} -r requirements-dev.txt
    pyenv rehash
}

install_pyenv() {
    local url="https://raw.githubusercontent.com/yyuu/pyenv-installer/master/bin/pyenv-installer"

    export PYENV_ROOT="${STORAGE_DIR}/.pyenv"
    export PATH="${PYENV_ROOT}/bin:$PATH"

    if ! hash pyenv 2>/dev/null; then
        echo ">>> [pyenv] Downloading and installing"
        curl -L "${url}" | bash
    else
        echo ">>> [pyenv] Updating"
        cd "${PYENV_ROOT}" && git pull && cd -
    fi

    echo ">>> [pyenv] Initializing"
    eval "$(pyenv init -)"
    eval "$(pyenv virtualenv-init -)"
}

install_python() {
    local version="$1"

    # To fix Mac error when building the package "libpython27.dylib does not exist"
    [ "${OSI}" = "osx" ] && export PYTHON_CONFIGURE_OPTS="--enable-shared"

    pyenv install --skip-existing "${version}"

    echo ">>> [pyenv] Using Python ${version}"
    pyenv global "${version}"
}

launch_tests() {
    echo ">>> Launching the tests suite"

    ${PIP} -r requirements-tests.txt
    ${PYTHON} -b -Wall -m pytest "${SPECIFIC_TEST}" \
        --cov-report= \
        --cov=nxdrive \
        --showlocals \
        --strict \
        --failed-first \
        --no-print-logs \
        -r fE \
        -v
}

start_nxdrive() {
    echo ">>> Starting Nuxeo Drive"

    export PYTHONPATH="${WORKSPACE_DRIVE}"
    python -m nxdrive
}

verify_python() {
    local version="$1"
    local cur_version=$(python --version 2>&1 | awk '{print $2}')

    echo ">>> Verifying Python version in use"

    if [ "${cur_version}" != "${version}" ]; then
        echo ">>> Python version ${cur_version}"
        echo ">>> Drive requires ${version}"
        exit 1
    fi

    # Also, check that primary modules are present (in case of wrong build)
    if ! check_import "import sqlite3"; then
        echo ">>> Uninstalling wrong Python version"
        pyenv uninstall -f "${PYTHON_DRIVE_VERSION}"
        install_python "${PYTHON_DRIVE_VERSION}"
    fi
}

# The main function, last in the script
main() {
    # Adjust PATH for Mac
    [ "${OSI}" = "osx" ] && export PATH="$PATH:/usr/local/bin"

    check_vars

    # The FinderSync extension build does not require extra setup
    if [ $# -eq 1 ]; then
        case "$1" in
            "--build-ext")
                build_extension
                exit 0
            ;;
        esac
    fi

    # Launch operations
    install_pyenv
    install_python "${PYTHON_DRIVE_VERSION}"
    verify_python "${PYTHON_DRIVE_VERSION}"

    if ! check_import "import sqlite3" >/dev/null; then
        echo ">>> Python installation failed, check compilation process."
        exit 1
    fi

    install_deps

    if ! check_import "import PyQt5" >/dev/null; then
        echo ">>> No PyQt5. Installation failed."
        exit 1
    fi

    if [ $# -eq 1 ]; then
        case "$1" in
            "--build") build_installer ;;
            "--start") start_nxdrive ;;
            "--tests") launch_tests ;;
        esac
    fi
}
