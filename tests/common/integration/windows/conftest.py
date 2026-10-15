from contextlib import contextmanager
from logging import getLogger
from pathlib import Path
from time import sleep

import pytest

import nxdrive  # noqa: F401  # Registers the server types used just below.
from nxdrive.drive.server_type import all_home_dirs

log = getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--executable",
        action="store",
        default="dist\\ndrive\\ndrive.exe",
        help="Path to the executable to test.",
    )


def accept_eula(config_dir):
    """Drop the marker telling the app the licence was already accepted.

    Without it the app blocks on the licence prompt, which no test can
    answer: the GUI dialog is modal and ``console`` mode reads stdin,
    which the spawned process does not have.

    The app picks its own home folder, so the marker goes in every home
    it may settle on as well as the per-test configuration folder.
    """
    homes = [Path(config_dir)]
    homes += [Path.home() / name for name in all_home_dirs()]
    for home in homes:
        home.mkdir(parents=True, exist_ok=True)
        (home / "eula_accepted").touch()


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
    accept_eula(path)

    @contextmanager
    def execute(cmd: str = final_exe, args: str = "", wait: int = 0):
        if "--nxdrive-home" not in args:
            args += f' --nxdrive-home="{path}"'
        if "--log-level-file" not in args:
            args += " --log-level-file=DEBUG"
        if "--ssl-no-verify" not in args:
            args += " --ssl-no-verify"
        args = args.strip()

        log.info(f"Starting {cmd!r} with args={args!r}")

        app = Application(backend="uia").start(f"{cmd} {args}")
        # Give the app time to start up (important for CI environments)
        sleep(2)
        try:
            yield app
            if wait > 0:
                sleep(wait)
        finally:
            app.kill()

    return execute
