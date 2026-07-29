"""Functional tests for :meth:`Manager.bind_server` against Alfresco."""

from pathlib import Path

import pytest


class TestBindServerHappyPath:
    def test_bind_creates_engine(
        self, manager_factory, alfresco_url, alfresco_user, alfresco_password
    ) -> None:
        manager = manager_factory(with_engine=False)
        conf = Path(manager.home) / "alfresco-conf"
        manager.bind_server(
            conf,
            alfresco_url,
            alfresco_user,
            password=alfresco_password,
            start_engine=False,
        )
        assert manager.engines


class TestBindServerBadCredentials:
    def test_wrong_password_raises(
        self, manager_factory, alfresco_url, alfresco_user
    ) -> None:
        manager = manager_factory(with_engine=False)
        conf = Path(manager.home) / "alfresco-conf"
        with pytest.raises(Exception):
            manager.bind_server(
                conf,
                alfresco_url,
                alfresco_user,
                password="definitely-not-the-password",
                start_engine=False,
            )
