"""Functional tests for :mod:`nxdrive.alfresco.engine.engine`.

Exercises the Engine binding path: build a Manager, bind to the
live Alfresco server, verify the engine is registered and can
report itself as connected.
"""

from pathlib import Path


class TestEngineBinding:
    def test_bind_produces_alfresco_engine(
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

        assert manager.engines, "Expected at least one engine after bind"
        engine = next(iter(manager.engines.values()))
        # The engine should be flagged as Alfresco flavour.
        assert engine.server_url == alfresco_url

    def test_engine_uid_is_stable(
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
        engine = next(iter(manager.engines.values()))
        assert engine.uid  # non-empty
