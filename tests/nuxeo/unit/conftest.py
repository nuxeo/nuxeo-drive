"""Nuxeo unit-test fixture bridge.

Re-exports the shared mock-DAO / MockEngine / MockManager / MockProcessor
fixtures from :mod:`tests.common.unit.conftest` so that
``tests/nuxeo/unit/test_*.py`` files can request them without any
conftest lookup path magic.

pytest resolves fixtures by name and does not automatically inherit
sibling ``conftest.py`` files (``tests/common/unit/`` is a sibling of
``tests/nuxeo/unit/``, not a parent), so we import them explicitly and
list them in ``__all__``.
"""

import pytest

from nxdrive.nuxeo.client.remote_client import Remote
from tests.common.unit.conftest import (  # noqa: F401 — re-exported fixtures
    MockProcessor,
    engine,
    engine_dao,
    manager,
    manager_dao,
    updater,
    upload,
)


@pytest.fixture()
def processor(request):
    """Provide the legacy Nuxeo processor fixture to Nuxeo tests only."""
    engine_fixture = request.getfixturevalue("engine")
    dao_fixture = request.getfixturevalue("engine_dao")
    processor = MockProcessor
    processor.engine = engine_fixture
    processor.remote = Remote
    processor.dao = dao_fixture
    return processor
