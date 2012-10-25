"""URL scheme / protocol event listener for the OSX platform"""
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


def register_protocol_handlers(controller):
    """Register the URL scheme listener using PyObjC"""
    # TODO: implement me as explained here:
    # http://pyobjc.sourceforge.net/examples/pyobjc-framework-WebKit/PyDocURLProtocol/source--PyDocURLProtocol.py.html
    log.debug("Protocol handler registration for OSX not yet implemented")
