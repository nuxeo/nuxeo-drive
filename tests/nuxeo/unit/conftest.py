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

from tests.common.unit.conftest import (  # noqa: F401 — re-exported fixtures
    engine,
    engine_dao,
    manager,
    manager_dao,
    processor,
    updater,
    upload,
)
