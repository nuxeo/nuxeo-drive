#!/bin/bash
# Shared functions for tools/$OSI/deploy_jenkins_slave.sh files.
#
# Usage: sh tools/$OSI/deploy_jenkins_slave.sh [ARG]
#
# Possible ARG:
#     --build: build the package
#     --build-ext: build the FinderSync extension (macOS only)
#     --install: install all dependencies
#     --start: start Nuxeo Drive
#     --tests: launch the tests suite
#
# See /docs/deployment.md for more information.
#

set -e

# Global variables
PYTHON="python -E -s"
PIP="${PYTHON} -m pip install --upgrade --upgrade-strategy=only-if-needed"

build_installer() {
    echo ">>> Building the release package"
    pyinstaller ndrive.spec --clean --noconfirm

    # Do some clean-up
    ${PYTHON} tools/cleanup_application_tree.py dist/ndrive
    if [ "${OSI}" = "osx" ]; then
        ${PYTHON} tools/cleanup_application_tree.py dist/*.app/Contents/Resources
        ${PYTHON} tools/cleanup_application_tree.py dist/*.app/Contents/MacOS

        # Move problematic folders out of Contents/MacOS
        ${PYTHON} tools/osx/fix_app_qt_folder_names_for_codesign.py dist/*.app

        # Remove broken symlinks pointing to an inexistant target
        find dist/*.app/Contents/MacOS -type l -exec sh -c 'for x; do [ -e "$x" ] || rm -v "$x"; done' _ {} +
    fi

    # Remove empty folders
    find dist/ndrive -depth -type d -empty -delete
    if [ "${OSI}" = "osx" ]; then
        find dist/*.app -depth -type d -empty -delete
    fi

    cd dist
    zip -9 -r "nuxeo-drive-${OSI}.zip" "ndrive"
    cd -

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
        export PYTHON_DRIVE_VERSION="3.6.8"  # XXX_PYTHON
    fi
    if [ "${WORKSPACE:=unset}" = "unset" ]; then
        echo "WORKSPACE not defined. Aborting."
        exit 1
    fi
    if [ "${OSI:=unset}" = "unset" ]; then
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

    if [ "${SPECIFIC_TEST:=unset}" = "unset" ] || [ "${SPECIFIC_TEST}" = "" ]; then
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
    # NXDRIVE-1521: pip 19.0.1 prevents PyInstaller installation
    ${PIP} pip==18.1
    ${PIP} -r requirements.txt
    ${PIP} -r requirements-dev.txt
    if [ "${INSTALL_RELEASE_ARG:=0}" != "1" ]; then
        ${PIP} -r requirements-tests.txt
        pyenv rehash
        pre-commit install
    fi
}

install_pyenv() {
    local url="https://raw.githubusercontent.com/yyuu/pyenv-installer/master/bin/pyenv-installer"
    local venv_plugin
    local venv_plugin_url="https://github.com/yyuu/pyenv-virtualenv.git"

    export PYENV_ROOT="${STORAGE_DIR}/.pyenv"
    export PATH="${PYENV_ROOT}/bin:$PATH"

    venv_plugin="${PYENV_ROOT}/plugins/pyenv-virtualenv"

    if [ "${INSTALL_ARG:=0}" = "1" ]; then
        if [ ! -d "${PYENV_ROOT}" ]; then
            echo ">>> [pyenv] Downloading and installing"
            curl -L "${url}" | bash
        else
            echo ">>> [pyenv] Updating"
            cd "${PYENV_ROOT}"
            git pull
            cd -
        fi
        if [ ! -d "${venv_plugin}" ]; then
            echo ">>> [pyenv] Installing virtualenv plugin"
            git clone "${venv_plugin_url}" "${venv_plugin}"
        fi
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
    if [ "${SPECIFIC_TEST}" = "tests" ]; then
        echo ">>> Checking the style"
        ${PYTHON} -m flake8 .

        echo ">>> Checking type annotations"
        ${PYTHON} -m mypy --ignore-missing-imports nxdrive
    fi

    echo ">>> Launching the tests suite"
    ${PYTHON} -bb -Wall -m pytest "${SPECIFIC_TEST}"
}

start_nxdrive() {
    echo ">>> Starting Nuxeo Drive"

    export PYTHONPATH="${WORKSPACE_DRIVE}"
    python -m nxdrive
}

verify_python() {
    local version="$1"
    local cur_version=$(python --version 2>&1 | head -n 1 | awk '{print $2}')

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
    [ "${OSI}" = "osx" ] && export PATH="$PATH:/usr/local/bin:/usr/sbin"

    check_vars

    # The FinderSync extension build does not require extra setup
    if [ $# -eq 1 ]; then
        case "$1" in
            "--build-ext")
                build_extension
                exit 0
            ;;
            "--install")
                export INSTALL_ARG="1"
            ;;
            "--install-release")
                export INSTALL_ARG="1"
                export INSTALL_RELEASE_ARG="1"
            ;;
        esac
    fi

    # Launch operations
    install_pyenv
    install_python "${PYTHON_DRIVE_VERSION}"
    verify_python "${PYTHON_DRIVE_VERSION}"

    if [ $# -eq 1 ]; then
        case "$1" in
            "--build") build_installer ;;
            "--install" | "--install-release")
                install_deps
                if ! check_import "import PyQt5" >/dev/null; then
                    echo ">>> No PyQt5. Installation failed."
                    exit 1
                fi
                ;;
            "--start") start_nxdrive ;;
            "--tests") launch_tests ;;
        esac
    fi
}
