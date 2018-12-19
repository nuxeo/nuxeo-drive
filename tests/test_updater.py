# coding: utf-8
import pytest

from nxdrive.updater.constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UP_TO_DATE,
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
}


@pytest.mark.parametrize(
    "current, server, nature, action_required, new",
    [
        # No version
        ("3.1.2", "", "release", "", ""),
        ("3.1.2", None, "release", "", ""),
        # Unexisting nature
        ("3.1.2", "10.10", "bar", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Unexisting version
        ("3.1.2", "0.0.0", "release", "", ""),
        ("3.1.2", "foo", "release", "", ""),
        ("3.1.2", "8.10-SNAPSHOT", "release", UPDATE_STATUS_DOWNGRADE_NEEDED, "3.0.1"),
        ("3.1.2", "10.3", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Version is up-to-date
        ("4.0.1", "7.10-HF44", "release", UPDATE_STATUS_UP_TO_DATE, ""),
        # Downgrade needed
        ("3.1.3", "7.10-HF10", "release", UPDATE_STATUS_DOWNGRADE_NEEDED, "3.1.1"),
        ("4.0.1", "7.10-HF49", "release", UPDATE_STATUS_DOWNGRADE_NEEDED, "4.0.0"),
        # Update available
        ("1.4.0622", "7.10", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.0.1"),
        ("3.0.1", "7.10-HF11", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        ("3.1.3", "7.10-HF44", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "4.0.1"),
        ("3.1.1", "10.3-SNAPSHOT", "release", UPDATE_STATUS_UPDATE_AVAILABLE, "3.1.3"),
        # Unknown version from versions.yml
        ("42.2.2", "10.3-SNAPSHOT", "release", "", ""),
        ("42.2.2", "5.6", "release", "", ""),
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
def test_get_update_status(current, server, nature, action_required, new):
    """get_update_status calls get_latest_compatible_version, 2 tests in one!"""
    action, version = get_update_status(current, VERSIONS, nature, server, True)
    assert action == action_required
    assert version == new
