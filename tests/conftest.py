import os
import platform
import shutil
import sqlite3
import sys
from datetime import datetime

import nuxeo.client
import nuxeo.operations
import pytest
from nuxeo.client import Nuxeo

from nxdrive.options import Options
from nxdrive.utils import adapt_datetime_iso, get_verify

from . import env

pytest_plugins = "tests.pytest_random"


# Operations cache
OPS_CACHE = None
SERVER_INFO = None

sqlite3.register_adapter(datetime, adapt_datetime_iso)

# Check __main.py__ for explanation
if sys.platform == "win32":
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """
    Disable xdist on macOS to prevent worker crashes with GUI tests.
    Qt event loop is not thread-safe; parallelism causes segfaults.
    """
    if platform.system() == "Darwin":
        # Prevent xdist from spawning workers
        config.option.dist = "no"
        if hasattr(config.option, "numprocesses"):
            config.option.numprocesses = 1


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """
    Force immediate process exit after session ends.

    Qt objects (QApplication, widgets) left alive at interpreter shutdown
    trigger a segfault (SIGSEGV / exit -11) during Python GC/cleanup.
    os._exit() skips interpreter teardown and avoids the crash while
    preserving the correct exit code. pytest-cov and other trylast hooks
    have already run by this point, so coverage reports are intact.
    """
    os._exit(int(exitstatus))


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Delete captured logs if the test is not in failure.
    It will help keeping the memory usage at a descent level.
    """

    # Execute the test
    outcome = yield

    # Get the report
    report = outcome.get_result()

    # Print failures immediately so CI logs contain traceback details
    # even if the full run is interrupted before pytest summary output.
    if report.failed and report.longrepr:
        print(
            f"\n[TEST {report.when.upper()} FAILED] {report.nodeid}",
            file=sys.stderr,
            flush=True,
        )
        try:
            print(report.longreprtext, file=sys.stderr, flush=True)
        except Exception:
            print(str(report.longrepr), file=sys.stderr, flush=True)

    if report.passed:
        # Remove captured logs to free memory
        report.sections = []
        outcome.force_result(report)


@pytest.fixture()
def tmp(tmp_path):
    """Use the original *tmp_path* fixture with automatic clean-up."""

    ssl_verify = get_verify()
    if Options.ssl_no_verify != ssl_verify:
        Options.ssl_no_verify = ssl_verify

    created_folders = []
    n = 0

    def _make_folder():
        nonlocal n
        path = tmp_path / str(n)
        created_folders.append(path)
        n += 1
        return path

    yield _make_folder

    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture(autouse=True)
def no_warnings(recwarn):
    """Fail on warning."""

    yield

    warnings = []
    for warning in recwarn:  # pragma: no cover
        message = str(warning.message)

        if "sentry_sdk" in warning.filename:
            continue
        elif "WaitForInputIdle" in message:
            # Happen while testing the integration on Windows, we can skip it:
            # "Application is not loaded correctly (WaitForInputIdle failed)"
            continue
        elif "type=SocketKind.SOCK_STREAM" in message:
            # Socket leaks on macOS, may need investigations
            continue
        elif "TerminalReporter.writer attribute is deprecated" in message:
            # Cannot understand if this is from our code or a pytest plugin,
            # let's wait for when it will fail :)
            continue
        elif "distutils Version classes are deprecated" in message:
            # Cannot understand if this is from our code or a pytest plugin,
            # let's wait for when it will fail :)
            continue
        elif "(rm_rf) error removing" in message:
            # First appeared with pytest 5.4.1
            continue
        elif "Unverified HTTPS request is being made to host" in message:
            continue
        elif "Cryptography will be significantly faster" in message:
            continue
        elif "unclosed database" in message:
            continue
        elif "unclosed <socket.socket" in message:
            # Python 3.13 emits this ResourceWarning in some HTTP teardown paths.
            # It is non-deterministic in functional runs and creates false negatives.
            continue

        warn = f"{warning.filename}:{warning.lineno} {message}"
        print(warn, file=sys.stderr)
        warnings.append(warn)

    assert not warnings


@pytest.fixture(autouse=True)
def cleanup_attrs(request):
    """
    Delete any attribute added in the test.
    It will help keeping the memory usage at a descent level.
    """

    # .instance for tests methods
    # .node     for tests functions
    test_case = request.instance or request.node
    attr_orig = set(test_case.__dict__.keys())

    yield

    # Note: if the test failed, this part will not be executed.

    attr_added = set(test_case.__dict__.keys()) - attr_orig
    if not attr_added:
        return

    for attr in attr_added:
        if attr.startswith("engine_"):
            engine = getattr(test_case, attr)
            if engine.remote:
                engine.remote.client._session.close()
        delattr(test_case, attr)


@pytest.fixture(scope="session")
def version() -> str:
    import nxdrive

    return nxdrive.__version__


@pytest.fixture(scope="session")
def nuxeo_url() -> str:
    """Retrieve the Nuxeo URL."""
    return env.NXDRIVE_TEST_NUXEO_URL.split("#")[0]


@pytest.fixture(scope="session")
def server(nuxeo_url):
    """
    Get the Nuxeo instance.

    For now, we do not allow to use another than Administrator:Administrator
    to prevent unexpected actions on critical servers.
    """
    verification_needed = get_verify()
    auth = (env.NXDRIVE_TEST_USERNAME, env.NXDRIVE_TEST_PASSWORD)
    server = Nuxeo(auth=auth, host=nuxeo_url, verify=verification_needed)
    server.client.set(schemas=["dublincore"])

    # Save bandwidth by caching operations details
    global OPS_CACHE
    if not OPS_CACHE:
        OPS_CACHE = server.operations.operations
        nuxeo.operations.API.ops = OPS_CACHE
    global SERVER_INFO
    if not SERVER_INFO:
        SERVER_INFO = server.client.server_info(ssl_verify=verification_needed)
        nuxeo.client.NuxeoClient._server_info = SERVER_INFO

    return server


@pytest.fixture
def app():
    """
    Fixture required to be able to process Qt events and quit smoothly the application.
    To use in "functional" and "unit" tests only.
    """
    from nxdrive.qt.imports import QCoreApplication, QTimer

    app = QCoreApplication.instance() or QCoreApplication([])

    # Little trick here! See Application.__init__() for details.
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    yield app

    timer.stop()
