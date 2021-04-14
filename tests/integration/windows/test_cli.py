from logging import getLogger

import pytest

from nxdrive.constants import WINDOWS

from .utils import fatal_error_dlg, main_window, share_metrics_dlg

if not WINDOWS:
    pytestmark = pytest.mark.skip("Windows only.")

log = getLogger(__name__)


def test_start_app(exe):
    with exe() as app:
        assert not fatal_error_dlg(app)
        assert share_metrics_dlg(app)

        # There should be the main window
        main = main_window(app)
        assert main.exists()
        main.close()


@pytest.mark.parametrize(
    "arg", ["invalid_AgUmeNt", "--invalid_AgUmeNt", "--invalid_AgUmeNt=42"]
)
def test_invalid_argument(exe, arg):
    with exe(args=arg) as app:
        assert fatal_error_dlg(app, with_details=False)


@pytest.mark.parametrize("arg", ["--log-level-file=42", "--delay=foo"])
def test_invalid_argument_value(exe, arg):
    with exe(args=arg) as app:
        assert fatal_error_dlg(app, with_details=False)


@pytest.mark.parametrize(
    "arg",
    [
        "--channel=alpha",
        "--channel=beta",
        "--channel=release",
        "--debug",
        "--debug-pydev",
        "--delay=42",
        "--force-locale=es",
        "--handshake-timeout=42",
        "--log-level-file=DEBUG",
        "--log-level-file=INFO",
        "--log-level-file=WARNING",
        "--log-level-file=ERROR",
        "--log-level-console=DEBUG",
        "--log-level-console=INFO",
        "--log-level-console=WARNING",
        "--log-level-console=ERROR",
        # --log-filename tested in test_argument_log_filename()
        "--locale=es",
        "--max-errors=42",
        "--nofscheck",
        # --nxdrive-home tested in test_argument_nxdrive_home()
        "--proxy-server=https://Alice:password@example.org:8888",
        "--ssl-no-verify",
        "--sync-and-quit",
        "--timeout=42",
        "--update-check-delay=42",
        "--update-site-url='https://example.org'",
        "--version",
        "-v",
    ],
)
def test_valid_argument_value(exe, arg):
    """Test all CLI arguments but those requiring a folder."""
    with exe(args=arg) as app:
        assert not fatal_error_dlg(app)
        share_metrics_dlg(app)


@pytest.mark.parametrize(
    "file", ["azerty.log", "$alice.log", "léa.log", "mi Kaël.log", "こん ツリ ^^.log"]
)
def test_argument_log_filename(exe, tmp, file):
    path = tmp()
    path.mkdir(parents=True, exist_ok=True)

    log = path / file
    arg = f'--log-filename="{log}"'

    with exe(args=arg) as app:
        assert not fatal_error_dlg(app)
        share_metrics_dlg(app)

    assert log.is_file()


@pytest.mark.parametrize("folder", ["azerty", "$alice", "léa", "mi Kaël", "こん ツリ ^^"])
def test_argument_nxdrive_home(exe, tmp, folder):
    path = tmp()
    path.mkdir(parents=True, exist_ok=True)

    home = path / folder
    arg = f'--nxdrive-home="{home}"'

    with exe(args=arg) as app:
        assert not fatal_error_dlg(app)
        share_metrics_dlg(app)

    assert home.is_dir()


@pytest.mark.parametrize(
    "arg",
    [
        "--beta-update-site-url='http://example.org'",
        "--beta-channel",
        "--consider-ssl-errors",
        "--max-sync-step=42",
        "--proxy-exceptions=unknwown",
        "--proxy-type=none",
    ],
)
def test_removed_argument(exe, arg):
    """Test removed/obsolete CLI arguments."""
    with exe(args=arg) as app:
        assert fatal_error_dlg(app, with_details=False)
