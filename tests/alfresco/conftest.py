"""Alfresco-specific pytest fixtures.

Imports :mod:`tests.env_alfresco` for server URLs, credentials, tenant and
site path. Provides the Alfresco REST client, admin auth, and cleanup
helpers used by ``tests/alfresco/{unit,functional,integration}``.

The whole subtree is guarded by ``ALFRESCO_URL``: when the env var is
empty (which is the default when running unit tests locally without a
live Alfresco server) every fixture that requires the server is marked
as skipped rather than blowing up with a connection error.
"""

from logging import getLogger

import pytest

from .. import env_alfresco as env

log = getLogger(__name__)


def _server_configured() -> bool:
    """True when the credentials needed to talk to Alfresco are set."""
    return bool(env.ALFRESCO_URL and env.ALFRESCO_USER and env.ALFRESCO_PASSWORD)


@pytest.fixture(scope="session")
def alfresco_url() -> str:
    """Return the configured Alfresco base URL or skip."""
    if not env.ALFRESCO_URL:
        pytest.skip("ALFRESCO_URL is not set; skipping Alfresco server tests.")
    return env.ALFRESCO_URL


@pytest.fixture(scope="session")
def alfresco_user() -> str:
    if not env.ALFRESCO_USER:
        pytest.skip("ALFRESCO_USER is not set; skipping Alfresco server tests.")
    return env.ALFRESCO_USER


@pytest.fixture(scope="session")
def alfresco_password() -> str:
    if not env.ALFRESCO_PASSWORD:
        pytest.skip("ALFRESCO_PASSWORD is not set; skipping Alfresco server tests.")
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
    the ``alfresco_url`` dep makes sure the test is skipped when the
    server is unreachable / credentials are missing.
    """
    from alfresco import Alfresco

    client = Alfresco(url=alfresco_url, auth=alfresco_auth)

    # Health check: skip the entire session when the server is down (e.g. 503).
    try:
        client.people.get("-me-")
    except Exception as exc:
        try:
            client.close()
        except Exception:
            pass
        pytest.skip(f"Alfresco server is not healthy, skipping functional tests: {exc}")

    yield client
    try:
        client.close()
    except Exception:  # pragma: no cover - defensive
        log.exception("Failed to close Alfresco client")


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


def pytest_collection_modifyitems(config, items):
    """Auto-skip functional / integration tests when the server is down."""
    if _server_configured():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "Alfresco server credentials not configured "
            "(set ALFRESCO_URL / ALFRESCO_USER / ALFRESCO_PASSWORD)."
        )
    )
    for item in items:
        path = str(item.fspath)
        if (
            "/tests/alfresco/functional/" in path
            or "/tests/alfresco/integration/" in path
        ):
            item.add_marker(skip_marker)
