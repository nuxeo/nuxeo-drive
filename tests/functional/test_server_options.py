from time import sleep
from unittest.mock import patch

import pytest

from nxdrive.behavior import Behavior
from nxdrive.feature import Feature
from nxdrive.options import Options
from nxdrive.poll_workers import ServerOptionsUpdater


def test_behavior(manager_factory):
    """Check that behaviors are well handled."""
    manager, engine = manager_factory()
    updater = ServerOptionsUpdater(manager)

    def enabled():
        return {"behavior": {"server_deletion": True}}

    def disabled():
        return {"behavior": {"server_deletion": False}}

    # Default value is True
    assert Behavior.server_deletion is True

    # Mimic the IT team disabling the behavior
    with patch.object(engine.remote, "get_server_configuration", new=disabled):
        updater._poll()
        assert Behavior.server_deletion is False

    # Mimic the IT team enabling back the behavior
    with patch.object(engine.remote, "get_server_configuration", new=enabled):
        updater._poll()
        assert Behavior.server_deletion is True

    # No-op check
    updater._poll()
    assert Behavior.server_deletion is True


def test_behavior_not_good(caplog, manager_factory):
    """Check that bad behaviors are skipped."""
    manager, engine = manager_factory()
    updater = ServerOptionsUpdater(manager)

    def unknown():
        return {"behavior": {"alien": True}}

    def bad_value():
        return {"behavior": {"server_deletion": "oui"}}

    # Default value is True
    assert Behavior.server_deletion is True

    # Mimic the IT team setting an unknown behavior
    with patch.object(engine.remote, "get_server_configuration", new=unknown):
        caplog.clear()
        updater._poll()

        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert record.message == "Invalid behavior: 'alien'"

    # Mimic the IT team setting a bad value for a known behavior
    with patch.object(engine.remote, "get_server_configuration", new=bad_value):
        caplog.clear()
        updater._poll()

        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert record.message == "Invalid behavior value: 'oui' (a boolean is required)"


@Options.mock()
@pytest.mark.parametrize(
    "feature, feat_name, default",
    [
        ("auto-update", "auto_update", True),
        ("Direct-Edit", "direct_edit", True),
        ("direct_transfer", "direct_transfer", True),
        ("s3", "s3", False),
    ],
)
def test_features(feature, feat_name, default, manager_factory):
    """Check that features are well handled."""
    manager, engine = manager_factory()
    updater = ServerOptionsUpdater(manager)
    opt_name = f"feature_{feat_name}"

    def enabled():
        return {"feature": {feature: default}}

    def toggled():
        return {"feature": {feature: not default}}

    # Check the default value
    assert getattr(Feature, feat_name) is default
    assert getattr(Options, opt_name) is default

    # Mimic the IT team toggling the feature's state
    with patch.object(engine.remote, "get_server_configuration", new=toggled):
        updater._poll()
        assert getattr(Feature, feat_name) is not default
        assert getattr(Options, opt_name) is not default

    # Mimic the IT team restoring back the feature's state
    with patch.object(engine.remote, "get_server_configuration", new=enabled):
        updater._poll()
        assert getattr(Feature, feat_name) is default
        assert getattr(Options, opt_name) is default

    # No-op
    updater._poll()
    assert getattr(Feature, feat_name) is default
    assert getattr(Options, opt_name) is default

    # Check when the feature is forced locally
    Options.set(opt_name, not default, setter="local")
    assert getattr(Feature, feat_name) is not default
    assert getattr(Options, opt_name) is not default

    # Check when the feature is forced locally (restoring the default value)
    Options.set(opt_name, default, setter="local")
    assert getattr(Feature, feat_name) is default
    assert getattr(Options, opt_name) is default

    # Then the server config has on more power on the feature state
    with patch.object(engine.remote, "get_server_configuration", new=toggled):
        updater._poll()
        assert getattr(Feature, feat_name) is default
        assert getattr(Options, opt_name) is default


@Options.mock()
def test_delay_remote_watcher(app, manager_factory):
    """Check that the delay, when set from the server config, is taken into account in the RemoteWatcher."""
    manager, engine = manager_factory()
    updater = ServerOptionsUpdater(manager)

    def config_2s():
        return {"delay": 2}

    def config_5s():
        return {"delay": 5}

    def handle_changes(*args, **kwargs):
        nonlocal count
        count += 1
        return True

    # Test the default value
    assert Options.delay == 30

    # Mimic the IT team setting new delays
    with manager:
        watcher = engine._remote_watcher
        with patch.object(watcher, "_handle_changes", new=handle_changes):

            # The delay is set to 5 seconds
            with patch.object(engine.remote, "get_server_configuration", new=config_5s):
                # Fetch the new config
                updater._poll()

                # Check the option is changed
                assert Options.delay == 5

                # Check remote checks are using the new delay
                count = 0
                engine.start()
                sleep(10)
                assert count > 1

            # The delay is set to 2 seconds
            with patch.object(engine.remote, "get_server_configuration", new=config_2s):
                # Fetch the new config
                updater._poll()

                # Check the option is changed
                assert Options.delay == 2

                # Check remote checks are using the new delay
                count = 0
                sleep(10)
                assert count >= 4
