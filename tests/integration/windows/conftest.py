from contextlib import contextmanager
from logging import getLogger

import pytest

from nxdrive.options import Options
from pywinauto.application import Application


log = getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--executable",
        action="store",
        default="dist\\ndrive\\ndrive.exe",
        help="Path to the executable to test.",
    )


@pytest.fixture
def final_exe(request):
    return request.config.getoption("--executable")


@pytest.fixture()
def exe(final_exe, tmp):
    """Run the application with optional arguments."""

    path = tmp() / "config"
    path.mkdir(parents=True, exist_ok=True)
    Options.nxdrive_home = path

    @contextmanager
    def execute(cmd=final_exe, args=None):
        log.info(f"Starting {cmd!r} with args={args!r}")

        if args:
            cmd += " " + args

        app = Application(backend="uia").start(cmd, timeout=30)
        try:
            yield app
        finally:
            app.kill(soft=True)

    return execute
