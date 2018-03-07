# coding: utf-8
""" Auto-update framework. """

from logging import getLogger
from nxdrive.options import Options

log = getLogger(__name__)


class UpdateError(Exception):
    """ Error handling class. """


def updater(*args, **kwargs):
    # type: (*Any, **Any) -> Updater
    """
    Factory returning a proper Updater class instance.
    It detects the plateform we are running on and choose the most adapted
    updater class.
    It then proxies its arguments to the class for instantiation.
    """

    if not Options.update_check_delay:
        # The user manually disabled the auto-update
        from .fake import Updater
        log.info('Update check delay is set to 0, disabling auto-update')
    else:
        import platform
        operating_system = platform.system().lower()

        if operating_system == 'darwin':
            from .darwin import Updater
        elif operating_system == 'windows':
            from .windows import Updater
        else:
            from .fake import Updater

    return Updater(*args, **kwargs)


__all__ = ('UpdateError', 'updater')
