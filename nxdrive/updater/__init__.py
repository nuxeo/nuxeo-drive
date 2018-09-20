# coding: utf-8
""" Auto-update framework. """

from logging import getLogger
from typing import Any, TYPE_CHECKING

from .utils import get_latest_compatible_version
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
        from .base import BaseUpdater as Updater  # noqa

        setattr(Updater, "_can_update", False)
        log.info("Update check delay is set to 0, disabling auto-update")
    else:
        import platform

        operating_system = platform.system().lower()

        if operating_system == "darwin":
            from .darwin import Updater  # type: ignore
        elif operating_system == "windows":
            from .windows import Updater  # type: ignore
        else:
            from .base import BaseUpdater as Updater  # type: ignore

            setattr(Updater, "_can_update", False)

    return Updater(*args, **kwargs)


__all__ = ("UpdateError", "get_latest_compatible_version", "updater")
