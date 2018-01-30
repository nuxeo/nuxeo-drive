#!/bin/sh -e
#
# Launch several QA tests. Sync with SonarCloud.
#
# Warning: do not execute this script manually but from Jenkins.
#

code_coverage() {
    echo ">>> [QA] Code coverage"
    coverage combine
    coverage xml
}

code_quality() {
    echo ">>> [QA] Code quality"
    pylint nuxeo-drive-client/nxdrive > pylint_report.txt
}

setup() {
    echo ">>> [QA] Setting up the virtualenv"
    virtualenv -p python2 venv
    . venv/bin/activate
    pip install coverage pylint
}

main() {
    setup
    code_coverage
    code_quality
}

main