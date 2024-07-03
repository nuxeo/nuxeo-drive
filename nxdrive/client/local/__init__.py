""" API to access local resources for synchronization. """
from .base import FileInfo, get

# Get the local client related to the current OS
LocalClient = get()

__all__ = ("FileInfo", "LocalClient")
