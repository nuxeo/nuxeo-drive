""" Auto-update framework. """

from logging import getLogger
from typing import TYPE_CHECKING

from ..constants import LINUX, MAC

if TYPE_CHECKING:
    from ..manager import Manager  # noqa
    from .base import BaseUpdater as Updater  # noqa

log = getLogger(__name__)


class UpdateError(Exception):
    """Error handling class."""


class UpdateIntegrityError(UpdateError):
    """Installer integrity error handling class."""

    def __init__(
        self, name: str, algo: str, remote_checksum: str, local_checksum: str
    ) -> None:
        self.name = name
        self.algo = algo
        self.remote_checksum = remote_checksum
        self.local_checksum = local_checksum

    def __str__(self) -> str:
        return (
            f"Integrity check failed [{self.algo}] for {self.name!r}: "
            f"good={self.remote_checksum!r}, found={self.local_checksum!r}"
        )


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


__all__ = ("UpdateError", "UpdateIntegrityError", "updater")
