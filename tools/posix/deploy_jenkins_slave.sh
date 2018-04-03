#!/bin/sh -eu
# Shared functions for tools/$OSI/deploy_jenkins_slave.sh files.
#
# Usage: sh tools/$OSI/deploy_jenkins_slave.sh [ARG]
#
# Possible ARG:
#     --build: build the package
#     --pip: launch a local PyPi server and test pip upload/installation
#     --start: start Nuxeo Drive
#     --tests: launch the tests suite
#
# See /docs/deployment.md for more information.
#

# Global variables
PYTHON="python -E -s"
PIP="${PYTHON} -m pip install --upgrade --upgrade-strategy=only-if-needed"
SERVER="https://nuxeo-jenkins-public-resources.s3.eu-west-3.amazonaws.com/drive"

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

check_sum() {
    # Calculate the MD5 sum of the file to check its integrity.
    # Note 1: we have to use Python from the host since we have no dev env installed.
    # Note 2: we use Python and not md5sum/md5 because we are not sure those tools are installed on the host.
    local file="$1"
    local filename="$(python -sBc "import os.path; print(os.path.basename('${file}'))")"
    local checksums="${WORKSPACE_DRIVE}/tools/checksums.txt"
    local md5="$(python -sBc "import hashlib; print(hashlib.md5(open('${file}', 'rb').read()).hexdigest())")"

    if [ $(grep -c "${md5}  ${filename}" "${checksums}") -ne 1 ]; then
        return 1
    fi
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
    if [ "${WORKSPACE_DRIVE:=unset}" = "unset" ]; then
        if [ -d "${WORKSPACE}/sources" ]; then
            export WORKSPACE_DRIVE="${WORKSPACE}/sources"
        elif [ -d "${WORKSPACE}/nuxeo-drive" ]; then
            export WORKSPACE_DRIVE="${WORKSPACE}/nuxeo-drive"
        else
            export WORKSPACE_DRIVE="${WORKSPACE}"
        fi
    fi
    export SIP_VERSION=${SIP_VERSION:=4.19.7}  # XXX: SIP_VERSION
    export STORAGE_DIR="${WORKSPACE}/deploy-dir"

    if [ "${COMPILE_WITH_DEBUG:=unset}" != "unset" ]; then
        echo "    COMPILE_WITH_DEBUG is set, be patient :)"
        export COMPILE_WITH_DEBUG="--debug"
        export OPT="-O0 -g -fno-inline -fno-strict-aliasing -Wnull-dereference"
        export PYTHON_CONFIGURE_OPTS="--with-pydebug"
    else
        export COMPILE_WITH_DEBUG=""
    fi

    echo "    PYTHON_DRIVE_VERSION = ${PYTHON_DRIVE_VERSION}"
    echo "    PYQT_VERSION         = ${PYQT_VERSION}"
    echo "    SIP_VERSION          = ${SIP_VERSION}"
    echo "    WORKSPACE            = ${WORKSPACE}"
    echo "    WORKSPACE_DRIVE      = ${WORKSPACE_DRIVE}"
    echo "    STORAGE_DIR          = ${STORAGE_DIR}"

    cd "${WORKSPACE_DRIVE}"

    if [ "${SPECIFIC_TEST:=unset}" = "unset" ] ||
       [ "${SPECIFIC_TEST}" = "" ] ||
       [ "${SPECIFIC_TEST}" = "nuxeo-drive-client/tests" ]; then
        export SPECIFIC_TEST="nuxeo-drive-client/tests"
    else
        echo "    SPECIFIC_TEST        = ${SPECIFIC_TEST}"
        export SPECIFIC_TEST="nuxeo-drive-client/tests/${SPECIFIC_TEST}"
    fi
}

download() {
    # Download one file and save its content to a given file name
    local url="$1"
    local output="$2"
    local try=1

    # 5 tries, because we are generous
    until [ ${try} -ge 6 ]; do
        if [ -f "${output}" ]; then
            if check_sum "${output}"; then
                return
            fi
            rm -rf "${output}"
        fi
        echo ">>> [$try/5] Downloading $url"
        echo "                   to $output"
        curl -L "$url" -o "$output" || true
        try=$(( ${try} + 1 ))
        sleep 5
    done

    echo ">>> Impossible to download and verify ${url}"
    return 1
}

extract() {
    # Extract a downloaded file
    local file="$1"
    local folder="$2"

    echo ">>> Extracting ${file}"
    echo "            to ${folder}"
    [ -d "${folder}" ] || tar zxf "${file}" -C "${STORAGE_DIR}"
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

install_pyqt() {
    local version="$1"
    local path="${STORAGE_DIR}"
    case "${OSI}" in
        "linux")
            url="${SERVER}/PyQt4_gpl_x11-${version}.tar.gz"
            path="${path}/PyQt4_gpl_x11-${version}"
            ;;
        "osx")
            url="${SERVER}/PyQt4_gpl_mac-${version}.tar.gz"
            path="${path}/PyQt4_gpl_mac-${version}"
            ;;
    esac
    local output="${path}.tar.gz"

    check_import "import PyQt4.QtWebKit" && return
    echo ">>> Installing PyQt ${version}"

    download "${url}" "${output}"
    extract "${output}" "${path}"

    cd "$path"

    echo ">>> [PyQt ${version}] Configuring"
    ${PYTHON} configure-ng.py "${COMPILE_WITH_DEBUG}" \
        --confirm-license \
        --no-designer-plugin \
        --no-docstrings \
        --no-python-dbus \
        --no-qsci-api \
        --no-tools

    echo ">>> [PyQt ${version}] Compiling"
    make -j 4

    echo ">>> [PyQt ${version}] Installing"
    make install

    cd "${WORKSPACE_DRIVE}"
}

install_python() {
    local version="$1"

    # To fix Mac error when building the package "libpython27.dylib does not exist"
    [ "${OSI}" = "osx" ] && export PYTHON_CONFIGURE_OPTS="--enable-shared"

    pyenv install --skip-existing "${version}"

    echo ">>> [pyenv] Using Python ${version}"
    pyenv global "${version}"
}

install_sip() {
    local version="$1"
    local url="${SERVER}/sip-${version}.tar.gz"
    local path="${STORAGE_DIR}/sip-${version}"
    local output="${path}.tar.gz"

    check_import "import os, sip; os._exit(not sip.SIP_VERSION_STR == '${SIP_VERSION}')" && return
    echo ">>> Installing SIP ${version}"

    download "${url}" "${output}"
    extract "${output}" "${path}"

    cd "${path}"

    echo ">>> [SIP ${version}] Configuring"
    ${PYTHON} configure.py --no-stubs

    echo ">>> [SIP ${version}] Compiling"
    make -j 4

    echo ">>> [SIP ${version}] Installing"
    make install

    cd "${WORKSPACE_DRIVE}"
}

launch_pip_tests() {
    local pid
    local cwd="$(pwd)/nuxeo-drive-client"
    local folder="$(mktemp -d 2>/dev/null || mktemp -d -t 'mytmpdir')"
    local port="1234"
    local url="http://localhost:${port}"
    local pip_args="install --isolated --upgrade --ignore-installed --extra-index-url ${url}"

    purge() {
        local pid=$1
        local ret=$2

        cd "${cwd}"

        kill "${pid}" || true
        deactivate || true
        rm -rf "${folder}" || true
        exit ${ret}
    }

    echo ">>> Launching pip tests in ${folder}"
    ${PIP} virtualenv

    echo ">>> [PyPi] Setting up the virtualenv"
    cd "${folder}"
    ${PYTHON} -m virtualenv --no-wheel pypi
    export VIRTUAL_ENV_DISABLE_PROMPT="true"  # macOS fix
    . pypi/bin/activate

    echo ">>> [PyPi] Removing old module installation"
    pip uninstall --yes nuxeo-drive || true

    echo ">>> [PyPi] Setting up the local server"
    mkdir pypi/packages
    pip install pypiserver
    pypi-server --disable-fallback -p "${port}" -P . -a . pypi/packages &
    pid=$!
    echo ">>> [PyPi] PID is ${pid}"

    echo ">>> [PyPi] Uploading to the local server"
    cd "${cwd}"
    python setup.py sdist upload -r "${url}" || purge ${pid} 1
    cd "${folder}"

    echo ">>> [PyPi] Installing from the local server"
    pip ${pip_args} nuxeo-drive || purge ${pid} 1

    echo ">>> [PyPi] Testing import"
    ret=$(${PYTHON} -c "import nxdrive ; print('${folder}' in nxdrive.__path__[0])")
    if [ "${ret}" = "False" ]; then
        echo ">>> [PyPi] Result: ERROR"
        echo "${folder}"
        ${PYTHON} -c "import nxdrive ; print(nxdrive.__path__[0])"
        purge ${pid} 1
    fi

    echo ">>> [PyPi] Result: OK"
    purge ${pid} 0 2>/dev/null
}

launch_tests() {
    echo ">>> Launching the tests suite"

    ${PIP} -r requirements-tests.txt
    ${PYTHON} -m pytest "${SPECIFIC_TEST}" \
        --cov-report= \
        --cov=nuxeo-drive-client/nxdrive \
        --showlocals \
        --strict \
        --failed-first \
        --no-print-logs \
        --log-level=CRITICAL \
        -r fE \
        -W error \
        -v
}

start_nxdrive() {
    echo ">>> Starting Nuxeo Drive"

    export PYTHONPATH="${WORKSPACE_DRIVE}/nuxeo-drive-client"
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

    # Launch operations
    check_vars
    install_pyenv
    install_python "${PYTHON_DRIVE_VERSION}"
    verify_python "${PYTHON_DRIVE_VERSION}"

    if ! check_import "import sqlite3" >/dev/null; then
        echo ">>> Python installation failed, check compilation process."
        exit 1
    fi

    # Some arguments do not need a whole setup
    if [ $# -eq 1 ]; then
        case "$1" in
            "--pip"  ) launch_pip_tests ;;
        esac
    fi

    install_sip "${SIP_VERSION}"
    install_pyqt "${PYQT_VERSION}"
    install_deps

    if ! check_import "import PyQt4.QtWebKit" >/dev/null; then
        echo ">>> No WebKit. Installation failed."
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
