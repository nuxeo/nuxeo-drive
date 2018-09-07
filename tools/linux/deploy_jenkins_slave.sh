#!/bin/sh -eu
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

export OSI="linux"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"

cleanup() {
    # Remove files from the package that are not needed and too big
    rm -rfv dist/ndrive/libQt5Bluetooth*
    rm -rfv dist/ndrive/libQt5Location*
    rm -rfv dist/ndrive/libQt5Nfc*
    rm -rfv dist/ndrive/libQt5Multimedia*
    rm -rfv dist/ndrive/libQt5Positioning*
    rm -rfv dist/ndrive/libQt5PrintSupport*
    rm -rfv dist/ndrive/libQt5QuickTest*
    rm -rfv dist/ndrive/libQt5Sensors*
    rm -rfv dist/ndrive/libQt5Test*
    rm -rfv dist/ndrive/libQt5WebChannel*
    rm -rfv dist/ndrive/libQt5WebEngine*
    rm -rfv dist/ndrive/libQt5XmlPatterns*
}

create_package() {
    # Create the final DEB
    echo ">>> [package] Creating the DEB file"
    echo ">>> [package] TODO The DEB creation for GNU/Linux is not yet implemented."
}

main "$@"
