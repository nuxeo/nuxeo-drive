#!/bin/sh -eu
# See tools/posix/deploy_jenkins_slave.sh for more informations and arguments.

export OSI="linux"

include="$(python -c "import os.path; print(os.path.realpath('$0').replace('/linux/', '/posix/'))")"
. "${include}"

main "$@"
