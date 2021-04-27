from enum import Flag, auto

# Update statuses
UPDATE_STATUS_INCOMPATIBLE_SERVER = "incompatible_server"
UPDATE_STATUS_UNAVAILABLE_SITE = "unavailable_site"
UPDATE_STATUS_UP_TO_DATE = "up_to_date"
UPDATE_STATUS_UPDATE_AVAILABLE = "update_available"
UPDATE_STATUS_UPDATING = "updating"
UPDATE_STATUS_WRONG_CHANNEL = "wrong_channel"


class AutoUpdateState(Flag):
    """Used to figure out if the application can be updated."""

    DISABLED = 0
    ENABLED = auto()
    FORCED = auto()


class Login(Flag):
    """Used to figure out which login endpoint is used for a given server."""

    NONE = 0
    OLD = auto()
    NEW = auto()
    UNKNOWN = auto()
