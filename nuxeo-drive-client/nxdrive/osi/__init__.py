import sys
import urllib
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path

log = get_logger(__name__)

NXDRIVE_EDIT_URL_PREFIX = ('nxdrive://edit/scheme/server[:port]'
                           '/webappname/')
NXDRIVE_EDIT_URL_PATTERN_1 = (NXDRIVE_EDIT_URL_PREFIX
                            + '[user/userName/]repo/repoName/nxdocid/docId/filename/fileName')
NXDRIVE_EDIT_URL_PATTERN_2 = NXDRIVE_EDIT_URL_PREFIX + 'fsitem/fsItemId'


# Protocol handler parsing


def parse_protocol_url(url_string):
    """Parse URL for which nxdrive is registered as a protocol handler
    Return None if url_string is not a supported URL pattern or raise a
    ValueError is the URL structure is invalid.
    """
    if "://" not in url_string:
        return None

    protocol_name, data_string = url_string.split('://', 1)
    if protocol_name != 'nxdrive':
        return None

    if '/' not in data_string:
        raise ValueError("Invalid nxdrive URL: " + url_string)

    command, data_string = data_string.split('/', 1)
    if command == 'edit':
        return parse_edit_protocol(data_string)
    else:
        raise ValueError("Unsupported command '%s' in " + url_string)


def parse_edit_protocol(data_string):
    """Parse a nxdrive://edit URL for quick editing of nuxeo documents"""
    invalid_msg = ('Invalid URL: got nxdrive://edit/%s while expecting %s'
                   ' or %s' % (data_string, NXDRIVE_EDIT_URL_PATTERN_1,
                               NXDRIVE_EDIT_URL_PATTERN_2))

    if '/' not in data_string:
        raise ValueError(invalid_msg)

    scheme, data_string = data_string.split('/', 1)
    if scheme not in ('http', 'https'):
        raise ValueError(
            invalid_msg + ' : scheme should be http or https')

    if '/nxdocid/' not in data_string and '/fsitem/' not in data_string:
        raise ValueError(invalid_msg)

    if '/nxdocid/' in data_string:
        if '/user/' in data_string:
            server_part, doc_part = data_string.split('/user/', 1)
            server_url = "%s://%s" % (scheme, server_part)
            user, doc_part = doc_part.split('/repo/', 1)
            repo, doc_part = doc_part.split('/nxdocid/', 1)
            doc_id, filename = doc_part.split('/filename/', 1)
            return dict(command='download_edit', server_url=server_url, user=user, repo=repo,
                        doc_id=doc_id, filename=filename)
        else:
            # Compatibility with old URL that doesn't contain user name
            server_part, doc_part = data_string.split('/repo/', 1)
            server_url = "%s://%s" % (scheme, server_part)
            repo, doc_part = doc_part.split('/nxdocid/', 1)
            doc_id, filename = doc_part.split('/filename/', 1)
            return dict(command='download_edit', server_url=server_url, user=None, repo=repo,
                        doc_id=doc_id, filename=filename)

    else:
        server_part, item_id = data_string.split('/fsitem/', 1)
        server_url = "%s://%s" % (scheme, server_part)
        item_id = urllib.unquote(item_id)  # unquote # sign
        return dict(command='edit', server_url=server_url, item_id=item_id)


class AbstractOSIntegration(object):
    def __init__(self, manager):
        self._manager = manager

    def register_startup(self):
        pass

    def unregister_startup(self):
        pass

    def register_protocol_handlers(self):
        pass

    def unregister_protocol_handlers(self):
        pass

    def register_contextual_menu(self):
        pass

    def unregister_contextual_menu(self):
        pass

    @staticmethod
    def get(manager):
        if sys.platform == "darwin":
            from nxdrive.osi.darwin import DarwinIntegration
            log.debug("Using Darwin OS integration")
            return DarwinIntegration(manager)
        elif sys.platform == "win32":
            from nxdrive.osi.windows import WindowsIntegration
            log.debug("Using Windows OS integration")
            return WindowsIntegration(manager)
        else:
            log.debug("Not using any OS integration")
            return AbstractOSIntegration(manager)
