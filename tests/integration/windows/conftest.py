from contextlib import contextmanager
from logging import getLogger

import pytest


log = getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--executable",
        action="store",
        default="dist\\ndrive\\ndrive.exe",
        help="Path to the executable to test.",
    )


@pytest.fixture()
def final_exe(request):
    return request.config.getoption("--executable")


@pytest.fixture()
def exe(final_exe, tmp):
    """Run the application with optional arguments."""

    # Use the import there to prevent pytest --last-failed to crash
    # when running on non Windows platforms
    from pywinauto.application import Application

    path = tmp() / "config"
    path.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def execute(cmd: str = final_exe, args: str = ""):
        if "--nxdrive-home" not in args:
            args += f' --nxdrive-home="{path}"'
        args = args.strip()

        log.info(f"Starting {cmd!r} with args={args!r}")

        app = Application(backend="uia").start(f"{cmd} {args}")
        try:
            yield app
        finally:
            app.kill(soft=True)

    return execute
