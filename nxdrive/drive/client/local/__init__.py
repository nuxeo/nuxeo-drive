#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""API to access local resources for synchronization."""

from .base import FileInfo, get

# Get the local client related to the current OS
LocalClient = get()

__all__ = ("FileInfo", "LocalClient")
