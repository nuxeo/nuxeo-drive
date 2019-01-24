# coding: utf-8
from enum import Flag, auto

# Update statuses
UPDATE_STATUS_DOWNGRADE_NEEDED = "downgrade_needed"
UPDATE_STATUS_UNAVAILABLE_SITE = "unavailable_site"
UPDATE_STATUS_UP_TO_DATE = "up_to_date"
UPDATE_STATUS_UPDATE_AVAILABLE = "update_available"
UPDATE_STATUS_UPDATING = "updating"


class Login(Flag):
    """ Used to figure out which login endpoint is used for a given server. """

    NONE = 0
    OLD = auto()
    NEW = auto()
    UNKNOWN = auto()
