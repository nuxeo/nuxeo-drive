#!/bin/bash
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

set -e

export OSI="linux"

. "$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"

create_package() {
    # Create the final DEB
    echo ">>> [package] Creating the DEB file"
    echo ">>> [package] TODO The DEB creation for GNU/Linux is not yet implemented."
}

main "$@"
