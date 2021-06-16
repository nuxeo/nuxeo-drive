#!/bin/bash
# Shared functions for tools/$OSI/deploy_ci_agent.sh files.
#
# Usage: sh tools/$OSI/deploy_ci_agent.sh [ARG]
#
# Possible ARG:
#     --build: build the package
#     --check: check AppImage conformity (GNU/Linux only)
#     --check-upgrade: check the auto-update works
#     --install: install all dependencies
#     --install-python: install only Python
#     --install-release: install all but test dependencies
#     --start: start Nuxeo Drive
#     --tests: launch the tests suite
#
# See /docs/deployment.md for more information.
#
# ---
#
# You can tweak tests checks by setting the SKIP envar:
#    - SKIP=rerun to not rerun failed test(s)
#
# There is no strict syntax about multiple skips (coma, coma + space, no separator, ... ).
#

set -e

# Global variables
PYTHON="python -Xutf8 -E -s"
PYTHON_VENV="./venv/bin/python -Xutf8 -E -s"
PYTHON_OPT="${PYTHON_VENV} -OO"
PIP="${PYTHON_OPT} -m pip install --no-cache-dir --upgrade --upgrade-strategy=only-if-needed --progress-bar=off"

build_installer() {
    local version

    echo ">>> Building the release package"
    ${PYTHON_VENV} -m PyInstaller ndrive.spec --clean --noconfirm

    # Check for freezer regressions
    ensure_correctness dist/ndrive

    # Do some clean-up
    ${PYTHON_VENV} tools/cleanup_application_tree.py dist/ndrive

    # Remove compiled QML files
    find dist -depth -type f -name "*.qmlc" -delete

    # Remove empty folders
    find dist -depth -type d -empty -delete

    if [ "${OSI}" = "osx" ]; then
        ${PYTHON_VENV} tools/cleanup_application_tree.py dist/*.app/Contents/Resources
        ${PYTHON_VENV} tools/cleanup_application_tree.py dist/*.app/Contents/MacOS

        # Move problematic folders out of Contents/MacOS
        ${PYTHON_VENV} tools/osx/fix_app_qt_folder_names_for_codesign.py dist/*.app

        # Remove broken symlinks pointing to an inexistent target
        find dist/*.app/Contents/MacOS -type l -exec sh -c 'for x; do [ -e "$x" ] || rm -v "$x"; done' _ {} +
    elif [ "${OSI}" = "linux" ]; then
        remove_excluded_files dist/ndrive
    fi

    # Stop now if we only want the application to be frozen (for integration tests)
    if [ "${FREEZE_ONLY:-0}" = "1" ]; then
        exit 0
    fi

    if [ "${ZIP_NEEDED:-0}" = "1" ]; then
        version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"
        cd dist
        zip -9 -q -r "nuxeo-drive-${OSI}-${version}.zip" "ndrive"
        cd -
    fi

    create_package
}

check_import() {
    # Check module import to know if it must be installed
    # i.e: check_import "from PyQt4 import QtWebKit"
    #  or: check_import "import cx_Freeze"
    local import="$1"
    local ret=0

    /bin/echo -n ">>> Checking Python code: ${import} ... "
    ${PYTHON_VENV} -c "${import}" 2>/dev/null || ret=1
    if [ ${ret} -ne 0 ]; then
        echo "Failed."
        return 1
    fi
    echo "OK."
}

check_upgrade() {
    # Ensure a new version can be released by checking the auto-update process.
    ${PYTHON_VENV} tools/scripts/check_update_process.py
}

check_vars() {
    # Check required variables
    if [ "${PYTHON_DRIVE_VERSION:-unset}" = "unset" ]; then
        export PYTHON_DRIVE_VERSION="3.9.5"  # XXX_PYTHON
    fi
    if [ "${WORKSPACE:-unset}" = "unset" ]; then
        if [ "${GITHUB_WORKSPACE:-unset}" != "unset" ]; then
            # Running from GitHub Actions
            WORKSPACE="$(dirname "${GITHUB_WORKSPACE}")"
            export WORKSPACE
        else
            echo "WORKSPACE not defined. Aborting."
            exit 1
        fi
    fi
    if [ "${OSI:-unset}" = "unset" ]; then
        echo "OSI not defined. Aborting."
        echo "Please do not call this script directly. Use the good one from 'tools/OS/deploy_ci_agent.sh'."
        exit 1
    fi
    if [ "${WORKSPACE_DRIVE:-unset}" = "unset" ]; then
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

    if [ "${SPECIFIC_TEST:-unset}" = "unset" ] || [ "${SPECIFIC_TEST}" = "" ]; then
        export SPECIFIC_TEST="tests"
    else
        echo "    SPECIFIC_TEST        = ${SPECIFIC_TEST}"
        export SPECIFIC_TEST="tests/${SPECIFIC_TEST}"
    fi

    if [ "${SKIP:-unset}" = "unset" ]; then
        export SKIP=""
    else
        echo "    SKIP                 = ${SKIP}"
    fi
}

create_venv() {
    # Create the isolated virtual environment
    # No-op if the folder already exists.
    # Note: the Python version will be checked later in the process to prevent any issues.
    ${PYTHON} -m venv --copies venv
}

install_deps() {
    echo ">>> Installing requirements"
    ${PIP} -r tools/deps/requirements-pip.txt
    ${PIP} -r tools/deps/requirements.txt
    ${PIP} -r tools/deps/requirements-dev.txt
    if [ "${INSTALL_RELEASE_ARG:-0}" != "1" ]; then
        ${PIP} -r tools/deps/requirements-tests.txt
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

    if [ "${INSTALL_ARG:-0}" = "1" ]; then
        if [ ! -d "${PYENV_ROOT}" ]; then
            echo ">>> [pyenv] Downloading and installing"
            curl -L "${url}" | bash
        else
            echo ">>> [pyenv] Updating"
            cd "${PYENV_ROOT}"
            # git is not available from the docker image, this is on purpose
            git pull || true
            cd -
        fi
        if [ ! -d "${venv_plugin}" ]; then
            echo ">>> [pyenv] Installing virtualenv plugin"
            git clone "${venv_plugin_url}" "${venv_plugin}"
        fi
    fi

    echo ">>> [pyenv] Initializing"
    # Ensure pyenv shims are added to PATH, see https://github.com/pyenv/pyenv/issues/1906
    eval "$(pyenv init --path)"
    eval "$(pyenv virtualenv-init -)"
}

install_python() {
    local version="$1"

    # To fix this error when building the package "libpythonXY.dylib does not exist"
    # Some of 3rd party tool like PyInstaller might require CPython installation
    # built with --enable-shared
    # Source: https://github.com/pyenv/pyenv/wiki#how-to-build-cpython-with---enable-shared
    export PYTHON_CONFIGURE_OPTS="--enable-shared"

    pyenv install --skip-existing "${version}"

    echo ">>> [pyenv] Using Python ${version}"
    pyenv global "${version}"
}

junit_arg() {
    local junit="tools/jenkins/junit/xml"
    local path="$1"
    local run="$2"

    if [ "${run}" != "" ]; then
        run=".${run}"
    fi
    echo "--junitxml=${junit}/${path}${run}.xml"
}

launch_test() {
    # Launch tests on a specific path. On failure, retry failed tests.
    local cmd="${PYTHON_VENV} -bb -Wall -m pytest"
    local path="${1}"
    local pytest_args="${2:-}"

    ${cmd} ${pytest_args} `junit_arg ${path} 1` "${path}" && return

    if should_run "rerun"; then
        # Will return 0 if rerun is needed else 1
        ${PYTHON_VENV} tools/check_pytest_lastfailed.py || return

        # Do not fail on error as all failures will be re-run another time at the end
        ${cmd} -n0 --last-failed --last-failed-no-failures none `junit_arg ${path} 2`  || true
    fi
}

launch_tests() {
    local ret=0

    rm -rf .pytest_cache

    # If a specific test is asked, just run it and bypass all over checks
    if [ "${SPECIFIC_TEST}" != "tests" ]; then
        echo ">>> Launching the specific tests"
        launch_test "${SPECIFIC_TEST}"
        return
    fi

    if should_run "tests"; then
        echo ">>> Launching synchronization functional tests, file by file"
        echo "    (first, run for each test file, failures are ignored to have"
        echo "     a whole picture of errors)"
        total="$(find tests/old_functional -name "test_*.py" | wc -l | tr -d '[:space:]')"
        number=1
        for test_file in $(find tests/old_functional -name "test_*.py"); do
            echo ""
            echo ">>> [${number}/${total}] Testing ${test_file} ..."
            launch_test "${test_file}" "-q --durations=3"
            number=$(( number + 1 ))
        done

        if should_run "rerun"; then
            echo ">>> Re-rerun failed tests"

            ${PYTHON_VENV} -m pytest --cache-show

            set +e
            # Will return 0 if rerun is needed else 1
            ${PYTHON_VENV} tools/check_pytest_lastfailed.py && \
                ${PYTHON_VENV} -bb -Wall -m pytest -n0 --last-failed --last-failed-no-failures none `junit_arg "final"`
            # The above command will exit with error code 5 if there is no failure to rerun
            ret=$?
            set -e
        fi

        # Do not fail on junit merge
        export TEST_SUITE="Drive"
        python tools/jenkins/junit/merge.py "tools/jenkins/junit/xml" || true

        if [ $ret -ne 0 ] && [ $ret -ne 5 ]; then
            exit 1
        fi
    fi
}

ensure_correctness() {
    # Ensure some vital files are present in the frozen directory.
    local app_dir="$1"

    echo ">>> [${app_dir}] Ensure the package is correct"

    # NXDRIVE-2056
    [ -d "${app_dir}/_struct" ] || (echo " !! Missing the '_struct' folder" ; exit 1)
    [ -d "${app_dir}/zlib" ] ||  (echo " !! Missing the 'zlib' folder" ; exit 1)
}

should_run() {
    # Return 0 if we should run the given action.
    local action

    action="$1"

    if should_skip "${action}"; then
        return 1
    else
        return 0
    fi

}

should_skip() {
    # Return 0 if we should skip the given action.
    local action
    local ret

    action="$1"

    if [ "${SKIP}" = "all" ]; then
        if [ "${action}" = "tests" ]; then
            # "all" does not affect "tests"
            ret=1
        else
            ret=0
        fi
    else
        case "${SKIP}" in
            *"${action}"*) ret=0 ;;
            *)             ret=1 ;;
        esac
    fi

    return ${ret}
}

start_nxdrive() {
    echo ">>> Starting Nuxeo Drive"

    export PYTHONPATH="${WORKSPACE_DRIVE}"
    ${PYTHON_OPT} -m nxdrive
}

verify_python() {
    local version="$1"
    local cur_version

    echo ">>> Verifying Python version in use"

    cur_version=$(${PYTHON_VENV} --version 2>&1 | head -n 1 | awk '{print $2}')
    if [ "${cur_version}" != "${version}" ]; then
        echo ">>> Python version '${cur_version}'"
        echo ">>> Drive requires '${version}'"
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
            "--check")
                check
                exit 0
            ;;
            "--install" | "--install-python")
                export INSTALL_ARG="1"
            ;;
            "--install-release")
                export INSTALL_ARG="1"
                export INSTALL_RELEASE_ARG="1"
            ;;
        esac
    fi

    # Ensure we are not running from within a virtual environment
    deactivate 2> /dev/null || true

    # Launch operations
    install_pyenv
    install_python "${PYTHON_DRIVE_VERSION}"
    create_venv
    verify_python "${PYTHON_DRIVE_VERSION}"

    if [ $# -eq 1 ]; then
        case "$1" in
            "--build") build_installer ;;
            "--check-upgrade") check_upgrade ;;
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
