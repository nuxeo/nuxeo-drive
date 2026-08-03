"""Alfresco-specific pytest fixtures.

Imports :mod:`tests.env_alfresco` for server URLs, credentials, tenant and
site path. Provides the Alfresco REST client, admin auth, and cleanup
helpers used by ``tests/alfresco/{unit,functional,integration}``.

The whole subtree is guarded by ``ALFRESCO_URL``: when the env var is
empty (which is the default when running unit tests locally without a
live Alfresco server) every functional / integration test **fails**
with a "no server available" message instead of silently skipping.
"""

from logging import getLogger

import pytest

from .. import env_alfresco as env

log = getLogger(__name__)

_NO_SERVER_MSG = (
    "No server available: Alfresco server credentials not configured "
    "(set ALFRESCO_URL / ALFRESCO_USER / ALFRESCO_PASSWORD)."
)


def _server_configured() -> bool:
    """True when the credentials needed to talk to Alfresco are set."""
    return bool(env.ALFRESCO_URL and env.ALFRESCO_USER and env.ALFRESCO_PASSWORD)


@pytest.fixture(scope="session")
def alfresco_url() -> str:
    """Return the configured Alfresco base URL or fail."""
    if not env.ALFRESCO_URL:
        pytest.fail("No server available: ALFRESCO_URL is not set.")
    return env.ALFRESCO_URL


@pytest.fixture(scope="session")
def alfresco_user() -> str:
    if not env.ALFRESCO_USER:
        pytest.fail("No server available: ALFRESCO_USER is not set.")
    return env.ALFRESCO_USER


@pytest.fixture(scope="session")
def alfresco_password() -> str:
    if not env.ALFRESCO_PASSWORD:
        pytest.fail("No server available: ALFRESCO_PASSWORD is not set.")
    return env.ALFRESCO_PASSWORD


@pytest.fixture(scope="session")
def alfresco_auth(alfresco_user: str, alfresco_password: str):
    """Return a ``BasicAuth`` object for the admin credentials."""
    from alfresco import BasicAuth

    return BasicAuth(alfresco_user, alfresco_password)


@pytest.fixture(scope="session")
def alfresco_client(alfresco_url: str, alfresco_auth):
    """A shared session-scoped ``alfresco.Alfresco`` client.

    Any test that touches the live server should depend on this fixture;
    the ``alfresco_url`` dep ensures the test fails when the server is
    unreachable / credentials are missing.
    """
    from alfresco import Alfresco

    client = Alfresco(url=alfresco_url, auth=alfresco_auth)

    # Health check: fail the entire session when the server is down (e.g. 503).
    try:
        client.people.get("-me-")
    except Exception as exc:
        try:
            client.close()
        except Exception:
            pass
        pytest.fail(f"No server available: Alfresco health check failed: {exc}")

    yield client
    try:
        client.close()
    except Exception:  # pragma: no cover - defensive
        log.exception("Failed to close Alfresco client")


@pytest.fixture(scope="session", autouse=True)
def _cleanup_stale_test_folders(alfresco_client):
    """Remove leftover nxdrive-func-tests-* folders before and after the run."""

    def _sweep():
        try:
            children = alfresco_client.nodes.list_children("-root-")
            for child in children:
                if child.name.startswith("nxdrive-func-tests-"):
                    try:
                        alfresco_client.nodes.delete(child.id, permanent=True)
                        log.info("[FIXTURE] Cleaned up folder %s", child.name)
                    except Exception as exc:
                        log.warning("[FIXTURE] Could not clean %s: %s", child.name, exc)
        except Exception as exc:
            log.warning("[FIXTURE] Folder cleanup failed: %s", exc)

    _sweep()
    yield
    _sweep()


@pytest.fixture()
def alfresco_test_folder(alfresco_client):
    """Create a temporary test folder under the repository root and delete it
    after tests complete."""
    import uuid

    folder_name = f"nxdrive-func-tests-{uuid.uuid4().hex[:8]}"
    log.info("[FIXTURE] Creating test folder %s under -root-", folder_name)
    node = alfresco_client.nodes.create_folder("-root-", folder_name)
    yield node
    # Cleanup: delete the folder and all its contents.
    try:
        alfresco_client.nodes.delete(node.id, permanent=True)
        log.info("[FIXTURE] Deleted test folder %s", folder_name)
    except Exception as exc:
        log.warning("[FIXTURE] Cleanup of %s failed: %s", folder_name, exc)


def pytest_runtest_setup(item):
    """Fail functional / integration tests early when the server is not configured."""
    if _server_configured():
        return
    path = str(item.fspath)
    if (
        "/tests/alfresco/functional/" in path
        or "/tests/alfresco/integration/" in path
    ):
        pytest.fail(_NO_SERVER_MSG)
