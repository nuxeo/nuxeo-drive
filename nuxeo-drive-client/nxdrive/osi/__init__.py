# coding: utf-8
import os
import platform
import sys
import urllib
from logging import getLogger

import psutil

from nxdrive.utils import version_compare

log = getLogger(__name__)

NXDRIVE_EDIT_URL_PREFIX = ('nxdrive://edit/scheme/server[:port]'
                           '/webappname/')
NXDRIVE_EDIT_URL_PATTERN_1 = (NXDRIVE_EDIT_URL_PREFIX
                        + '[user/userName/]repo/repoName/nxdocid/docId/filename/fileName[/downloadUrl/downloadUrl]')
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
    raise ValueError("Unsupported command '%s' in " + url_string)


def parse_edit_protocol(data_string):
    """Parse a nxdrive://edit URL for quick editing of nuxeo documents"""
    invalid_msg = ('Invalid URL: got nxdrive://edit/%s while expecting %s'
                   ' or %s' % (data_string, NXDRIVE_EDIT_URL_PATTERN_1,
                               NXDRIVE_EDIT_URL_PATTERN_2))
    try:
        scheme, data_string = data_string.split('/', 1)
        if scheme not in ('http', 'https'):
            raise ValueError(
                invalid_msg + ' : scheme should be http or https')

        if '/nxdocid/' in data_string:
            if '/user/' in data_string:
                server_part, doc_part = data_string.split('/user/', 1)
                server_url = "%s://%s" % (scheme, server_part)
                user, doc_part = doc_part.split('/repo/', 1)
                repo, doc_part = doc_part.split('/nxdocid/', 1)
                doc_id, doc_part = doc_part.split('/filename/', 1)
                if '/downloadUrl/' in doc_part:
                    filename, download_url = doc_part.split('/downloadUrl/', 1)
                else:
                    # TODO: https://jira.nuxeo.com/browse/NXDRIVE-237
                    filename = doc_part
                    download_url = None
                return dict(command='download_edit', server_url=server_url, user=user, repo=repo,
                            doc_id=doc_id, filename=filename, download_url=download_url)
            # Compatibility with old URL that doesn't contain user name nor download URL
            # TODO: https://jira.nuxeo.com/browse/NXDRIVE-237
            server_part, doc_part = data_string.split('/repo/', 1)
            server_url = "%s://%s" % (scheme, server_part)
            repo, doc_part = doc_part.split('/nxdocid/', 1)
            doc_id, filename = doc_part.split('/filename/', 1)
            return dict(command='download_edit', server_url=server_url, user=None, repo=repo,
                        doc_id=doc_id, filename=filename, download_url=None)

        server_part, item_id = data_string.split('/fsitem/', 1)
        server_url = "%s://%s" % (scheme, server_part)
        item_id = urllib.unquote(item_id)  # unquote # sign
        return dict(command='edit', server_url=server_url, item_id=item_id)
    except:
        raise ValueError(invalid_msg)


class AbstractOSIntegration(object):

    zoom_factor = 1.0

    def __init__(self, manager):
        self._manager = manager

    def register_startup(self):
        pass

    @staticmethod
    def is_partition_supported(folder):
        return True

    def uninstall(self):
        self.unregister_contextual_menu()
        self.unregister_desktop_link()
        self.unregister_folder_link(None)
        self.unregister_protocol_handlers()
        self.unregister_startup()

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

    def register_folder_link(self, folder_path, name=None):
        pass

    def unregister_folder_link(self, name):
        pass

    def register_desktop_link(self):
        pass

    def unregister_desktop_link(self):
        pass

    @staticmethod
    def is_same_partition(folder1, folder2):
        return os.stat(folder1).st_dev == os.stat(folder2).st_dev

    def get_system_configuration(self):
        return dict()

    @staticmethod
    def os_version_below(version):
        return version_compare(AbstractOSIntegration.get_os_version(), version) < 0

    @staticmethod
    def os_version_above(version):
        return version_compare(AbstractOSIntegration.get_os_version(), version) > 0

    @staticmethod
    def get_os_version():
        if AbstractOSIntegration.is_mac():
            return platform.mac_ver()[0]
        if AbstractOSIntegration.is_windows():
            """
            5.0.2195    Windows 2000
            5.1.2600    Windows XP
                        Windows XP 64-Bit Edition Version 2002 (Itanium)
            5.2.3790    Windows Server 2003
                        Windows XP x64 Edition (AMD64/EM64T)
                        Windows XP 64-Bit Edition Version 2003 (Itanium)
            6.0.6000    Windows Vista
            6.0.6001    Windows Vista SP1
                        Windows Server 2008
            6.1.7600    Windows 7
                        Windows Server 2008 R2
            6.1.7601    Windows 7 SP1
                        Windows Server 2008 R2 SP1
            6.2.9200    Windows 8
                        Windows Server 2012
            6.3.9200    Windows 8.1
                        Windows Server 2012 R2
            6.3.9600    Windows 8.1 with Update 1
            6.4.        Windows 10
            """
            return platform.win32_ver()[1]

        raise RuntimeError('Cannot determine GNU/Linux version')

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
            log.debug('Using macOS integration')
            return DarwinIntegration(manager)
        elif AbstractOSIntegration.is_windows():
            from nxdrive.osi.windows.windows import WindowsIntegration
            log.debug('Using Windows OS integration')
            return WindowsIntegration(manager)

        log.debug('Not using any OS integration')
        return AbstractOSIntegration(manager)
