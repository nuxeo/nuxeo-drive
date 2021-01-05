""" Auto-update framework. """

from logging import getLogger
from typing import TYPE_CHECKING

from ..constants import LINUX, MAC

if TYPE_CHECKING:
    from ..manager import Manager  # noqa
    from .base import BaseUpdater as Updater  # noqa

log = getLogger(__name__)


class UpdateError(Exception):
    """ Error handling class. """


def updater(manager: "Manager", /) -> "Updater":
    """
    Factory returning a proper Updater class instance.
    It detects the platform we are running on and chooses the most suited
    updater class.
    It then proxies its arguments to the class for instantiation.
    """

    if LINUX:
        from . import linux

        return linux.Updater(manager)

    if MAC:
        from . import darwin

        return darwin.Updater(manager)

    from . import windows

    return windows.Updater(manager)


__all__ = ("UpdateError", "updater")
