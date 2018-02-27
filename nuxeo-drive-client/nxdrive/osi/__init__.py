# coding: utf-8
import os
import re
import sys
import urllib
from logging import getLogger


log = getLogger(__name__)

# TODO: move to direct_edit.py, no need for these constants
NXDRIVE_EDIT_URL_BASE = 'nxdrive://edit/scheme/server[:port]/webappname/'
NXDRIVE_EDIT_URL_PATTERN_1 = ('{}user/userName/repo/repoName/nxdocid/'
                              'docId/filename/fileName[/downloadUrl/'
                              'downloadUrl]').format(NXDRIVE_EDIT_URL_BASE)
NXDRIVE_EDIT_URL_PATTERN_2 = '{}fsitem/fsItemId'.format(NXDRIVE_EDIT_URL_BASE)
NXDRIVE_ACCESS_URL_PATTERN = 'nxdrive://access/filepath'


NXDRIVE_PROTOCOL_REGEX = [('nxdrive://(?P<cmd>edit)/(?P<scheme>\w*)/'
                           '(?P<server>.*)/user/(?P<username>\w*)/repo/'
                           '(?P<repo>\w*)/nxdocid/(?P<docid>(\d|[a-f]|-)*)/'
                           'filename/(?P<filename>[^/]*)(/downloadUrl/'
                           '(?P<download>.*)|)'),

                          ('nxdrive://(?P<cmd>edit)/(?P<scheme>\w*)/'
                           '(?P<server>.*)/fsitem/(?P<fsitem>.*)'),

                          'nxdrive://(?P<cmd>share_link)/(?P<path>.*)',

                          'nxdrive://(?P<cmd>access)/(?P<path>.*)']

def parse_protocol_url(url_string):  # TODO: move to direct_edit.py
    """Parse URL for which nxdrive is registered as a protocol handler

    Return None if url_string is not a supported URL pattern or raise a
    ValueError is the URL structure is invalid.
    """
    if not url_string.startswith('nxdrive://'):
        return None

    parsed_url = None
    for regex in NXDRIVE_PROTOCOL_REGEX:
        parsed_url = re.match(regex, url_string)
        if parsed_url:
            break

    if not parsed_url:
        raise ValueError(
            'Unsupported command {!r} in protocol handler'.format(url_string))

    parsed_url = parsed_url.groupdict()
    cmd = parsed_url.get('cmd')
    if cmd == 'edit':
        return parse_edit_protocol(parsed_url, url_string)
    if cmd in ('access', 'share_link'):
        return dict(command=cmd, filepath=parsed_url.get('path'))


def parse_edit_protocol(parsed_url, url_string):
    """ Parse a nxdrive://edit URL for quick editing of nuxeo documents. """
    scheme = parsed_url.get('scheme')
    if scheme not in ('http', 'https'):
        raise ValueError(
            'Invalid command {} : scheme should be http or https'.format(
                url_string))

    server_url = '{}://{}'.format(scheme, parsed_url.get('server'))

    fsitem = parsed_url.get('fsitem')
    if fsitem:
        fsitem = urllib.unquote(fsitem)
        return dict(command='edit', server_url=server_url, item_id=fsitem)

    return dict(command='download_edit', server_url=server_url,
                user=parsed_url.get('username'),
                repo=parsed_url.get('repo'),
                doc_id=parsed_url.get('docid'),
                filename=parsed_url.get('filename'),
                download_url=parsed_url.get('download'))


class AbstractOSIntegration(object):

    zoom_factor = 1.0

    def __init__(self, manager):
        self._manager = manager

    def register_startup(self):
        pass

    def unregister_startup(self):
        pass

    @staticmethod
    def is_partition_supported(folder):
        return True

    def uninstall(self):
        """ Several action to do before uninstalling Drive. """

        # macOS only
        self.unregister_contextual_menu()
        self.unregister_protocol_handlers()
        self.unregister_startup()

        # Windows and macOS
        self.unregister_folder_link(None)

    def register_protocol_handlers(self):
        pass

    def unregister_protocol_handlers(self):
        pass

    def register_contextual_menu(self):
        pass

    def unregister_contextual_menu(self):
        pass

    def register_folder_link(self, folder_path, name=None):
        pass

    def unregister_folder_link(self, name):
        pass

    @staticmethod
    def is_same_partition(folder1, folder2):
        return os.stat(folder1).st_dev == os.stat(folder2).st_dev

    def get_system_configuration(self):
        return dict()

    @staticmethod
    def is_mac():
        return sys.platform == 'darwin'

    @staticmethod
    def is_windows():
        return sys.platform == 'win32'

    @staticmethod
    def is_linux():
        return not (AbstractOSIntegration.is_mac()
                    or AbstractOSIntegration.is_windows())

    @staticmethod
    def get(manager):
        if AbstractOSIntegration.is_mac():
            from nxdrive.osi.darwin.darwin import DarwinIntegration
            integration, nature = DarwinIntegration, 'macOS'
        elif AbstractOSIntegration.is_windows():
            from nxdrive.osi.windows.windows import WindowsIntegration
            integration, nature = WindowsIntegration, 'Windows'
        else:
            integration, nature = AbstractOSIntegration, 'None'

        log.debug('OS integration type: %s', nature)
        return integration(manager)
