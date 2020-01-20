# coding: utf-8
""" Auto-update framework. """

from logging import getLogger
from typing import TYPE_CHECKING, Any

from ..constants import LINUX, MAC
from ..options import Options

if TYPE_CHECKING:
    from .base import BaseUpdater as Updater  # noqa

log = getLogger(__name__)


class UpdateError(Exception):
    """ Error handling class. """


def updater(*args: Any, **kwargs: Any) -> "Updater":
    """
    Factory returning a proper Updater class instance.
    It detects the platform we are running on and chooses the most suited
    updater class.
    It then proxies its arguments to the class for instantiation.
    """

    if not Options.update_check_delay:
        # The user manually disabled the auto-update
        from . import base

        setattr(base.BaseUpdater, "_can_update", False)
        log.info("Update check delay is set to 0, disabling auto-update")
        return base.BaseUpdater(*args, **kwargs)

    if LINUX:
        from . import linux

        return linux.Updater(*args, **kwargs)

    if MAC:
        from . import darwin

        return darwin.Updater(*args, **kwargs)

    from . import windows

    return windows.Updater(*args, **kwargs)


__all__ = ("UpdateError", "updater")
