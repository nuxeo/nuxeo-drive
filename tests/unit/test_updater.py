import pytest

from nxdrive.options import Options
from nxdrive.updater.constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_WRONG_CHANNEL,
    Login,
)
from nxdrive.updater.utils import get_update_status

VERSIONS = {
    "1.3.0424": {"type": "release", "min": "5.8"},
    "1.3.0524": {"type": "release", "min": "5.9.1"},
    "1.4.0622": {"type": "release", "min": "5.9.2"},
    "2.4.2b1": {"type": "beta", "min": "9.2"},
    "2.5.0b1": {"type": "beta", "min": "9.2"},
    "2.5.0b2": {"type": "beta", "min": "9.2"},
    "3.0.1": {"type": "release", "min": "7.10"},
    "3.1.1": {"type": "release", "min": "7.10-HF1", "max": "7.10-HF44"},
    "3.1.2": {"min_all": {"10.3": "10.3-SNAPSHOT"}, "type": "release"},
    "3.1.3": {
        "type": "release",
        "min": "7.10-HF11",
        "min_all": {"7.10": "7.10-HF11", "8.10": "8.10", "9.10": "9.10"},
    },
    "4.0.0": {
        "type": "release",
        "min_all": {"7.10": "7.10-HF44", "8.10": "8.10-HF35", "9.10": "9.10-HF15"},
    },
    "4.0.1": {
        "type": "release",
        "min_all": {"7.10": "7.10-HF44", "8.10": "8.10-HF35", "9.10": "9.10-HF15"},
        "max_all": {"7.10": "7.10-HF48"},
    },
    "4.0.2.13": {"type": "alpha", "min": "9.10"},
    "4.0.2.14": {"type": "alpha", "min": "9.10"},
    "4.0.3.1": {"type": "alpha", "min": "10.10"},
    "4.0.3.6": {"type": "alpha", "min": "10.11"},
    "4.0.3.12": {"type": "alpha", "min": "10.11"},
    "4.2.0": {"type": "release", "min": "10.12"},
    "4.2.1": {"type": "release", "min": "10.13"},
    "4.3.4": {"type": "beta", "min": "10.12"},
}


@pytest.mark.parametrize(
    "current, server, channel, action_required, new",
    [
        # No version
        ("3.1.2", "", "release", "", ""),
        ("3.1.2", None, "release", "", ""),
        # Unexisting channel, fallback on the release one
        ("3.1.2", "10.10", "bar", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Unexisting version
        ("3.1.2", "0.0.0", "release", "", ""),
        ("3.1.2", "foo", "release", "", ""),
        (
            "3.1.2",
            "8.10-SNAPSHOT",
            "release",
            UPDATE_STATUS_INCOMPATIBLE_SERVER,
            "3.0.1",
        ),
        ("3.1.2", "10.3", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Version is up-to-date
        ("4.0.1", "7.10-HF44", "release", UPDATE_STATUS_UP_TO_DATE, ""),
        # Downgrade needed
        ("3.1.3", "7.10-HF10", "release", UPDATE_STATUS_INCOMPATIBLE_SERVER, "3.1.1"),
        ("4.0.1", "7.10-HF49", "release", UPDATE_STATUS_INCOMPATIBLE_SERVER, "4.0.0"),
        # Update available
        ("1.4.0622", "7.10", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.0.1"),
        ("3.0.1", "7.10-HF11", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        ("3.1.3", "7.10-HF44", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "4.0.1"),
        ("3.1.1", "10.3-SNAPSHOT", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Unknown version from versions.yml
        ("42.2.2", "10.3-SNAPSHOT", "release", "", ""),
        ("42.2.2", "5.6", "release", "", ""),
        # Wrong channel
        ("4.0.2.13", "10.1", "release", UPDATE_STATUS_WRONG_CHANNEL, "3.1.3"),
        # Beta
        ("2.4.2b1", "9.2", "beta", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        ("2.5.0b1", "9.2", "beta", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Alpha
        ("4.0.2.13", "9.10", "alpha", UPDATE_STATUS_UPDATE_AVAILABLE, "4.0.2.14"),
        ("4.0.3.1", "10.10", "alpha", UPDATE_STATUS_UP_TO_DATE, ""),
        ("4.0.3.3", "10.10", "alpha", "", ""),
        ("4.0.3.1", "10.11", "alpha", UPDATE_STATUS_UPDATE_AVAILABLE, "4.0.3.12"),
    ],
)
def test_get_update_status(current, server, channel, action_required, new):
    """get_update_status calls get_latest_version and get_compatible_versions, 2 tests in one!"""
    action, version = get_update_status(current, VERSIONS, channel, server, Login.NEW)
    assert action == action_required
    assert version == new


@Options.mock()
@pytest.mark.parametrize(
    "current, desired, action_required, new",
    [
        # Centralized
        ("4.3.4", "4.2.0", UPDATE_STATUS_UPDATE_AVAILABLE, "4.2.0"),
        ("4.3.4", "4.2.2", UPDATE_STATUS_UPDATE_AVAILABLE, "4.2.2"),
        ("4.3.4", "4.3.4", UPDATE_STATUS_UP_TO_DATE, ""),
    ],
)
def test_get_update_status_centralized_channel(current, desired, action_required, new):
    """Test the Centralized channel."""
    Options.client_version = desired
    assert Options.client_version == desired
    action, version = get_update_status(
        current, VERSIONS, "centralized", "10.12", Login.NEW
    )
    assert action == action_required
    assert version == new


@Options.mock()
def test_get_update_status_centralized_channel_wrong_client_version():
    """Test the Centralized channel with a client_version too low."""
    # Must be >= 4.2.0
    Options.client_version = "4.0.3.12"

    # The options is not updated, protected by the option's callback
    assert Options.client_version is None

    action, version = get_update_status(
        "4.3.4", VERSIONS, "centralized", "10.12", Login.NEW
    )

    # As the client_version is not set, it falls back to the release channel.
    # The latest release is 4.2.0 (4.3.4 is beta).
    # As the version in use is from the beta channel, the user is asked
    # to either downgrade to the release channel or continue using that beta channel.
    assert action == UPDATE_STATUS_WRONG_CHANNEL
    assert version == "4.2.0"


@Options.mock()
def test_get_update_status_centralized_channel_client_version_from_other_channel():
    """Test the Centralized channel with a client_version from a channel other than release."""
    Options.client_version = "4.3.4"
    action, version = get_update_status(
        "4.0.3.12", VERSIONS, "centralized", "10.12", Login.NEW
    )

    # As the client_version is set, it is allowed to update to another channel (here alpha -> beta)
    assert action == UPDATE_STATUS_UPDATE_AVAILABLE
    assert version == "4.3.4"


@Options.mock()
def test_get_update_status_centralized_channel_without_client_version():
    """Test the Centralized channel when no client_version is set,
    it should fall back on the release channel.
    """
    assert Options.client_version is None
    action, version = get_update_status(
        "4.0.1", VERSIONS, "centralized", "10.15", Login.NEW
    )
    assert action == UPDATE_STATUS_UPDATE_AVAILABLE
    assert version == "4.2.1"


@Options.mock()
def test_get_update_status_centralized_channel_wrong_server():
    """Test the Centralized channel when the desired version is not compatible with the server."""
    Options.client_version = "4.2.1"
    assert Options.client_version == "4.2.1"
    action, version = get_update_status(
        "4.3.4", VERSIONS, "centralized", "10.11", Login.NEW
    )
    assert action == UPDATE_STATUS_INCOMPATIBLE_SERVER
    assert version == "4.2.1"


def test_get_update_status_versions_is_none():
    """BaseUpdater.versions may be set to None, before NXDRIVE-1682."""
    # No version
    current, server, channel, action_required, new = "3.1.2", "", "release", "", ""
    action, version = get_update_status(current, None, channel, server, Login.NONE)
    assert action == action_required
    assert version == new
