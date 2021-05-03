"""
Launch Nuxeo Drive functional tests against a running Nuxeo instance.

Steps executed:
    - setup test environment variables
    - run the integration tests directly from sources
"""

import subprocess
import sys


def set_environment():
    # Convenient way to try a specific test without having to abort and start a new job.
    # import os
    #
    # os.environ["SPECIFIC_TEST"] = "tests/..."
    return


def run_tests_from_source():
    """Launch the tests suite."""

    osi = sys.platform

    if osi.startswith("linux"):
        install = ["sh", "../tools/linux/deploy_ci_agent.sh", "--install"]
        tests = ["sh", "../tools/linux/deploy_ci_agent.sh", "--tests"]
    elif osi == "darwin":
        install = ["sh", "../tools/osx/deploy_ci_agent.sh", "--install"]
        tests = ["sh", "../tools/osx/deploy_ci_agent.sh", "--tests"]
    elif osi == "win32":
        install = [
            "powershell",
            ".\\..\\tools\\windows\\deploy_ci_agent.ps1",
            "-install",
        ]
        tests = [
            "powershell",
            ".\\..\\tools\\windows\\deploy_ci_agent.ps1",
            "-tests",
        ]
    else:
        raise RuntimeError("OS not supported")

    subprocess.check_call(install)
    subprocess.check_call(tests)


if __name__ == "__main__":
    set_environment()
    run_tests_from_source()
