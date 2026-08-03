"""Functional-test fixtures for the Alfresco flavour.

Session-scoped fixtures build one authenticated
:class:`alfresco.Alfresco` client per test session.  Function-scoped
fixtures build ephemeral test folders / files under
the repository root and delete them on tear-down.

All fixtures raise ``pytest.skip`` when
``env.ALFRESCO_URL / _USER / _PASSWORD`` are not set, so the whole
suite is safe to collect on machines without a live server (see
:func:`tests.alfresco.conftest.pytest_collection_modifyitems`).
"""

from logging import getLogger
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import pytest

from nxdrive.drive.manager import Manager

log = getLogger(__name__)


@pytest.fixture()
def unique_name() -> Callable[[str], str]:
    """Return a callable that builds unique, prefix-safe test-artefact names."""

    def _make(prefix: str = "test") -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

    return _make


@pytest.fixture()
def temp_folder(alfresco_client, alfresco_test_folder, unique_name):
    """Create a scratch folder under the test root and delete it on tear-down."""
    name = unique_name("ndt-folder")
    folder = alfresco_client.nodes.create_folder(alfresco_test_folder.id, name)
    log.info("[FIXTURE] Created scratch folder %s (%s)", name, folder.id)
    try:
        yield folder
    finally:
        try:
            alfresco_client.nodes.delete(folder.id)
        except Exception as exc:  # pragma: no cover - server-state cleanup
            log.warning("Cleanup of %s failed: %s", folder.id, exc)


@pytest.fixture()
def manager_factory(
    tmp_path, alfresco_client, alfresco_url, alfresco_user, alfresco_password
):
    """Yield a factory that builds :class:`Manager` instances bound to the
    live Alfresco server.  Each manager is automatically closed on teardown.

    Depends on ``alfresco_client`` so that the session-level health check
    skips the suite when the Alfresco server is unavailable.
    """
    created: list[Manager] = []

    def _make(
        home: Optional[Path] = None,
        with_engine: bool = True,
    ) -> Manager:
        m = Manager(str(home or tmp_path))
        m.set_config("deletion_behavior", "delete_server")
        m.dao.store_bool("show_deletion_prompt", False)
        created.append(m)
        if with_engine:
            m.bind_server(
                tmp_path / "alfresco-conf",
                alfresco_url,
                alfresco_user,
                password=alfresco_password,
                start_engine=False,
            )
        return m

    try:
        yield _make
    finally:
        for m in created:
            try:
                m.close()
            except Exception as exc:  # pragma: no cover
                log.warning("Manager close failed: %s", exc)
