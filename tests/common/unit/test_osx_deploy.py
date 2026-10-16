#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="Bash is required")
SCRIPT = Path(__file__).resolve().parents[3] / "tools/osx/deploy_ci_agent.sh"
DEFINITIONS = (
    SCRIPT.read_text().split("# Global variables", 1)[1].rsplit('\nmain "$@"', 1)[0]
)


def run_bash(body, posix=False, **env):
    return subprocess.run(
        [
            BASH,
            *(["--posix"] if posix else []),
            "-c",
            "set -e\n" + DEFINITIONS + "\n" + body,
        ],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize("failures", [0, 1, 2, 3])
@pytest.mark.parametrize("status", [1, 124])
def test_codesign_retries(failures, status):
    result = run_bash(
        """
        attempts=0
        timeout() {
            attempts=$((attempts + 1))
            printf 'TIMEOUT:%s\\n' "$1"
            shift
            printf 'ARG:%s\\n' "$@"
            [ "${attempts}" -gt "${FAILURES}" ] || return "${STATUS}"
        }
        sleep() { echo "SLEEP:$1"; }
        codesign_with_retry "Developer ID with spaces" --force "App with spaces.app"
        echo COMPLETED
        """,
        FAILURES=str(failures),
        STATUS=str(status),
        CODESIGN_TIMEOUT="120",
    )
    attempts = min(failures + 1, 3)
    assert result.stdout.count("TIMEOUT:120") == attempts
    assert result.stdout.count("ARG:--timestamp\n") == attempts
    assert result.stdout.count("ARG:Developer ID with spaces\n") == attempts
    assert result.stdout.count("ARG:App with spaces.app\n") == attempts
    assert ("SLEEP:5" in result.stdout) == (failures >= 1)
    assert ("SLEEP:10" in result.stdout) == (failures >= 2)
    assert "SLEEP:15" not in result.stdout
    assert result.returncode == (status if failures == 3 else 0)
    assert ("COMPLETED" in result.stdout) == (failures < 3)
    if failures:
        assert "Attempt 1/3 failed" in result.stderr
    if failures == 3:
        assert "Attempt 3/3 failed" in result.stderr


@pytest.mark.parametrize("command", ["timeout", "gtimeout"])
@pytest.mark.parametrize("duration", ["", "240"])
def test_codesign_timeout_command(command, duration):
    result = run_bash(
        f"""
        PATH=""
        {command}() {{ printf 'TIMEOUT:%s\\n' "$1"; }}
        codesign_with_retry identity app
        """,
        CODESIGN_TIMEOUT=duration,
    )
    assert result.returncode == 0
    assert f"TIMEOUT:{duration or '120'}" in result.stdout


def test_codesign_missing_timeout():
    result = run_bash('PATH=""\ncodesign_with_retry identity app')
    assert result.returncode == 127
    assert "install coreutils with Homebrew" in result.stderr


def test_codesign_real_timeout():
    if not shutil.which("timeout") and not shutil.which("gtimeout"):
        pytest.skip("timeout or gtimeout is required")
    result = run_bash(
        """
        CODESIGN="/bin/sleep"
        sleep() { :; }
        codesign_with_retry 2
        echo COMPLETED
        """,
        CODESIGN_TIMEOUT="0.05",
    )
    assert result.returncode == 124
    assert result.stdout.count(">>> [sign] Attempt") == 3
    assert "COMPLETED" not in result.stdout


@pytest.fixture
def package(tmp_path):
    app = tmp_path / "dist/Hyland Drive for Alfresco.app"
    for name in (
        "MacOS/binary with\nnewline",
        "Resources/plugin.dylib",
        "Resources/ui.qml",
    ):
        path = app / "Contents" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return app


@pytest.mark.parametrize(
    "failure",
    ["", "binary with\nnewline", "plugin.dylib", "ui.qml", "appex", ".app", ".dmg"],
)
@pytest.mark.parametrize("posix", [False, True])
def test_create_package_signing(package, failure, posix):
    result = run_bash(
        """
        build_extension() { :; }
        prepare_signing() { :; }
        prepare_signing_from_scratch() { :; }
        mkdir() { :; }
        mv() { :; }
        rm() { :; }
        cp() { :; }
        ln() { :; }
        hdiutil() { :; }
        du() { printf '1\\tapp\\n'; }
        grep() { echo '__alfresco_version__ = "1.0"'; }
        spctl() { :; }
        notarize() { echo NOTARIZED; }
        sleep() { echo "SLEEP:$1"; }
        timeout() { echo "TIMEOUT:$1"; shift; "$@"; }
        codesign() {
            case "$1" in --display|--verbose=4) return 0 ;; esac
            printf 'SIGNED:<%s>\\n' "$@"
            if [ -n "${FAILURE}" ]; then
                for arg; do
                    case "${arg}" in *"${FAILURE}") return 42 ;; esac
                done
            fi
        }
        create_package alfresco
        echo COMPLETED
        """,
        posix=posix,
        WORKSPACE_DRIVE=str(package.parents[1]),
        WORKSPACE=str(package.parents[1]),
        GITHUB_WORKSPACE=str(package.parents[1]),
        SIGNING_ID="Developer ID with spaces",
        PYTHON_VENV="notarize",
        FAILURE=failure,
    )
    assert result.returncode == (42 if failure else 0)
    assert ("COMPLETED" in result.stdout) == (not failure)
    assert ("NOTARIZED" in result.stdout) == (not failure)
    if failure:
        assert result.stdout.count("SLEEP:5") >= 1
        assert result.stdout.count("SLEEP:10") >= 1
        assert result.stderr.count("Attempt 3/3 failed") >= 1
    else:
        assert result.stdout.count("TIMEOUT:120") == 8
        assert (
            f"SIGNED:<{package}/Contents/MacOS/binary with\nnewline>" in result.stdout
        )


def test_create_package_signing_retries_ordered_failures(package):
    result = run_bash(
        """
        build_extension() { :; }
        prepare_signing() { :; }
        prepare_signing_from_scratch() { :; }
        mkdir() { :; }
        mv() { :; }
        rm() { :; }
        cp() { :; }
        ln() { :; }
        hdiutil() { :; }
        du() { printf '1\\tapp\\n'; }
        grep() { echo '__alfresco_version__ = "1.0"'; }
        spctl() { :; }
        notarize() { echo NOTARIZED; }
        sleep() { :; }
        timeout() { shift; "$@"; }
        codesign() {
            case "$1" in --display|--verbose=4) return 0 ;; esac
            for arg; do
                case "${arg}" in *"plugin.dylib") plugin_signed=1 ;; esac
            done
            for arg; do
                case "${arg}" in *"binary with"*)
                    [ "${plugin_signed:-0}" -eq 1 ] || return 42
                    ;;
                esac
            done
            return 0
        }
        create_package alfresco
        echo COMPLETED
        """,
        WORKSPACE_DRIVE=str(package.parents[1]),
        WORKSPACE=str(package.parents[1]),
        GITHUB_WORKSPACE=str(package.parents[1]),
        SIGNING_ID="Developer ID with spaces",
        PYTHON_VENV="notarize",
    )
    assert result.returncode == 0
    assert "COMPLETED" in result.stdout
    assert "NOTARIZED" in result.stdout
    assert "Retrying" in result.stdout


def test_create_package_unsigned(package):
    result = run_bash(
        """
        build_extension() { :; }
        prepare_signing() { :; }
        prepare_signing_from_scratch() { :; }
        mkdir() { :; }
        mv() { :; }
        rm() { :; }
        cp() { :; }
        ln() { :; }
        hdiutil() { :; }
        du() { printf '1\\tapp\\n'; }
        grep() { echo '__alfresco_version__ = "1.0"'; }
        codesign_with_retry() { echo UNEXPECTED_SIGNING; return 99; }
        create_package alfresco
        echo COMPLETED
        """,
        WORKSPACE_DRIVE=str(package.parents[1]),
        WORKSPACE=str(package.parents[1]),
        GITHUB_WORKSPACE=str(package.parents[1]),
        SIGNING_ID="unset",
    )
    assert result.returncode == 0
    assert "COMPLETED" in result.stdout
    assert "UNEXPECTED_SIGNING" not in result.stdout
