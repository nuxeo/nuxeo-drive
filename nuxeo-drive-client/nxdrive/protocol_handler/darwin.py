"""URL scheme / protocol event listener for the OSX platform

This is taken from the argv_emulation code of py2app and modified to run as a
generic eventlistener loops that can work in a thread in parallel to the main
synchronization loop of nxdrive.

NOTE: This module uses ctypes and not the Carbon modules in the stdlib because
the latter don't work in 64-bit mode and are also not available with python
3.x.

"""
from nxdrive.logging_config import get_logger
log = get_logger(__name__)

NXDRIVE_SCHEME = 'nxdrive'


def register_protocol_handlers(controller):
    """Register the URL scheme listener using PyObjC"""
    try:
        from Foundation import NSBundle
        from LaunchServices import LSSetDefaultHandlerForURLScheme
    except ImportError:
        log.warn("Cannot registed %r scheme: missing OSX Foundation module",
                 NXDRIVE_SCHEME)
        return

    bundle_id = NSBundle.mainBundle().bundleIdentifier()
    if bundle_id == 'org.python.python':
        log.debug("Skipping URL scheme registration as this program "
                  " was launched from the Python OSX app bundle")
        return
    LSSetDefaultHandlerForURLScheme(NXDRIVE_SCHEME, bundle_id)
    log.debug("Registered bundle '%s' for URL scheme '%s'", bundle_id,
              NXDRIVE_SCHEME)
