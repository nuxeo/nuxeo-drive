from contextlib import contextmanager
from logging import getLogger
from pathlib import Path
from time import sleep

import pytest

log = getLogger(__name__)


def pytest_addoption(parser):
    print(f"pytest_addoption called with parser={parser}")
    parser.addoption(
        "--executable",
        action="store",
        default="dist\\ndrive\\ndrive.exe",
        help="Path to the executable to test.",
    )


@pytest.fixture()
def final_exe(request):
    print(f"final_exe fixture called with request={request}")
    return request.config.getoption("--executable")


@pytest.fixture()
def exe(final_exe, tmp):
    """Run the application with optional arguments."""
    print(f"exe fixture called with final_exe={final_exe}, tmp={tmp}")

    # Use the import there to prevent pytest --last-failed to crash
    # when running on non Windows platforms
    from pywinauto.application import Application

    path = tmp() / "config"
    path.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def execute(cmd: str = final_exe, args: str = "", wait: int = 0):
        print(f"execute called with cmd={cmd}, args={args}, wait={wait}")
        if "--nxdrive-home" not in args:
            args += f' --nxdrive-home="{path}"'
        if "--log-level-file" not in args:
            args += " --log-level-file=DEBUG"
        if "--ssl-no-verify" not in args:
            args += " --ssl-no-verify"
        args = args.strip()

        log.info(f"Starting {cmd!r} with args={args!r}")
        print(f"Starting {cmd!r} with args={args!r}")

        app = Application(backend="uia").start(f"{cmd} {args}")
        # Give the app time to start up (important for CI environments)
        sleep(2)
        try:
            yield app
            if wait > 0:
                sleep(wait)
        finally:
            # Check for crash.state file in all possible locations
            crash_locations = [
                Path.home() / ".nuxeo-drive" / "crash.state",
                Path.home() / ".drive" / "crash.state",
                path / "crash.state",
            ]
            for crash_file in crash_locations:
                if crash_file.exists():
                    try:
                        content = crash_file.read_text(encoding="utf-8", errors="replace")
                        print(f"\n{'=' * 60}")
                        print(f"CRASH STATE FILE FOUND at {crash_file}:")
                        print(content)
                        print(f"{'=' * 60}\n")
                    except Exception as e:
                        print(f"Could not read crash.state at {crash_file}: {e}")
            app.kill()

    return execute
