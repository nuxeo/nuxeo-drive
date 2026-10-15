#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Fixtures for common functional tests.

Re-exports server-specific fixtures so that tests under
``tests/common/functional/`` have access to them when collected
alongside the nuxeo (or alfresco) test directories.
"""

from tests.nuxeo.functional.conftest import (  # noqa: F401
    faker,
    manager_factory,
    obj_factory,
    user_factory,
)
