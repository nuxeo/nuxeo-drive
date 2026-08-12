"""Nuxeo-specific pytest fixtures.

Imports :mod:`tests.env_nuxeo` for server URLs, credentials, ``WS_DIR`` and
document types. Provides the Nuxeo Python client, the ``server`` fixture,
operations cache, and cleanup helpers used by
``tests/nuxeo/{unit,functional,integration}``.
"""
