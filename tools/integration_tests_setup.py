# coding: utf-8
"""
Launch Nuxeo Drive functional tests against a running Nuxeo instance.

Steps executed:
    - setup test environment variables
    - run the auto-update test directly from sources
    - run the integration tests directly from sources
"""

import os
import subprocess
import sys


def set_environment():
    # Convenient way to try a specific test without having to abort and start a new job.
    os.environ["SPECIFIC_TEST"] = "tests"


def run_tests_from_source():
    """ Launch the tests suite. """

    if sys.platform.startswith("linux"):
        check_upgrade = []
        install = ["sh", "../tools/linux/deploy_jenkins_slave.sh", "--install"]
        tests = ["sh", ",../tools/linux/deploy_jenkins_slave.sh", "--tests"]
    elif sys.platform == "darwin":
        check_upgrade = [
            "sh",
            "../tools/osx/deploy_jenkins_slave.sh",
            "--check-upgrade",
        ]
        install = ["sh", "../tools/osx/deploy_jenkins_slave.sh", "--install"]
        tests = ["sh", ",../tools/osx/deploy_jenkins_slave.sh", "--tests"]
    else:
        check_upgrade = [
            "powershell",
            ".\\..\\tools\\windows\\deploy_jenkins_slave.ps1",
            "-check_upgrade",
        ]
        install = [
            "powershell",
            ".\\..\\tools\\windows\\deploy_jenkins_slave.ps1",
            "-install",
        ]
        tests = [
            "powershell",
            ".\\..\\tools\\windows\\deploy_jenkins_slave.ps1",
            "-tests",
        ]

    if os.getenv("NXDRIVE_CHECK_AUTO_UPDATE"):
        subprocess.check_call(check_upgrade)
    else:
        subprocess.check_call(install)
        subprocess.check_call(tests)


if __name__ == "__main__":
    set_environment()
    run_tests_from_source()
