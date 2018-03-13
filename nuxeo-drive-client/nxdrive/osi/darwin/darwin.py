# coding: utf-8
import os
import sys
import urllib2
from logging import getLogger

import AppKit
import objc
from AppKit import NSRegisterServicesProvider, NSURLPboardType
from Foundation import NSObject, NSURL

from ...utils import normalized_path
from .. import AbstractOSIntegration

log = getLogger(__name__)


def serviceSelector(fn):
    # this is the signature of service selectors
    return objc.selector(fn, signature='v@:@@o^@')


class RightClickService(NSObject):

    @serviceSelector
    def openInBrowser_userData_error_(self, pboard, data, error):
        log.trace('openInBrowser has been called')
        try:
            path = self.get_file_path(pboard)
            log.debug('Accessing online: %s', path)
            from PyQt4.QtCore import QCoreApplication
            QCoreApplication.instance().show_metadata(path)
        except:
            log.exception('Right click service error')

    @serviceSelector
    def copyShareLink_userData_error_(self, pboard, data, error):
        log.trace('copyShareLink has been called')
        try:
            path = self.get_file_path(pboard)
            log.debug('Copying share-link for: %s', path)
            from PyQt4.QtCore import QCoreApplication
            QCoreApplication.instance().manager.copy_share_link(path)
        except:
            log.exception('Right click service error')

    @objc.python_method
    def get_file_path(self, pboard):
        types = pboard.types()
        if NSURLPboardType in types:
            pboardArray = pboard.propertyListForType_(NSURLPboardType)
            log.error('Retrieve property list %r', pboardArray)
            for value in pboardArray:
                if not value:
                    continue
                # TODO Replug prompt_metadata on this one
                url = NSURL.URLWithString_(value)
                if url:
                    return url.path()
                if value.startswith('file://'):
                    value = value[7:]
                return urllib2.unquote(value)


class DarwinIntegration(AbstractOSIntegration):
    NXDRIVE_SCHEME = 'nxdrive'
    NDRIVE_AGENT_TEMPLATE = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1.0">'
        '<dict>'
        '<key>Label</key>'
        '<string>org.nuxeo.drive.agentlauncher</string>'
        '<key>RunAtLoad</key>'
        '<true/>'
        '<key>Program</key>'
        '<string>%s</string>'
        '</dict>'
        '</plist>'
    )

    def _get_agent_file(self):
        return os.path.join(
            os.path.expanduser('~/Library/LaunchAgents'),
            self._manager.get_cf_bundle_identifier() + '.plist')

    def register_startup(self):
        """
        Register the Nuxeo Drive.app as a user Launch Agent.
        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
        """

        agent = os.path.join(
            os.path.expanduser('~/Library/LaunchAgents'),
            self._manager.get_cf_bundle_identifier() + '.plist')
        if os.path.isfile(agent):
            return

        agents_folder = os.path.dirname(agent)
        if not os.path.exists(agents_folder):
            log.debug('Making launch agent folder %r', agents_folder)
            os.makedirs(agents_folder)

        exe_path = os.path.realpath(os.path.dirname(sys.executable))
        log.debug('Registering %r for startup in %r', exe_path, agent)
        with open(agent, 'wb') as f:
            f.write(self.NDRIVE_AGENT_TEMPLATE % exe_path)

    def unregister_startup(self):
        agent_filepath = self._get_agent_file()
        if os.path.exists(agent_filepath):
            os.remove(agent_filepath)

    def _register_services(self):
        NSRegisterServicesProvider(RightClickService.alloc().init(),
                                   self._manager.app_name)
        # Refresh services
        AppKit.NSUpdateDynamicServices()

    def register_contextual_menu(self):
        # Register the service that handle the right click
        self._register_services()

    def unregister_contextual_menu(self):
        # Specified in the Bundle plist
        pass

    def register_protocol_handlers(self):
        """Register the URL scheme listener using PyObjC"""
        from Foundation import NSBundle
        from LaunchServices import LSSetDefaultHandlerForURLScheme

        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if bundle_id == 'org.python.python':
            log.debug('Skipping URL scheme registration as this program '
                      ' was launched from the Python OSX app bundle')
            return
        LSSetDefaultHandlerForURLScheme(self.NXDRIVE_SCHEME, bundle_id)
        log.debug('Registered bundle %r for URL scheme %r', bundle_id,
                  self.NXDRIVE_SCHEME)

    def unregister_protocol_handlers(self):
        # Don't unregister, should be removed when Bundle removed
        pass

    @staticmethod
    def is_partition_supported(folder):
        if folder is None:
            return False
        result = False
        to_delete = not os.path.exists(folder)
        try:
            if to_delete:
                os.mkdir(folder)
            if not os.access(folder, os.W_OK):
                import stat
                os.chmod(folder, stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
                         | stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR)
            import xattr
            attr = 'drive-test'
            xattr.setxattr(folder, attr, attr)
            if xattr.getxattr(folder, attr) == attr:
                result = True
            xattr.removexattr(folder, attr)
        finally:
            if to_delete:
                try:
                    os.rmdir(folder)
                except:
                    pass
        return result

    def register_folder_link(self, folder_path, name=None):
        from LaunchServices import LSSharedFileListInsertItemURL
        from LaunchServices import kLSSharedFileListItemBeforeFirst
        from LaunchServices import CFURLCreateWithString

        favorites = self._get_favorite_list() or []
        if not favorites:
            log.warning('Could not fetch the Finder favorite list.')
            return

        folder_path = normalized_path(folder_path)
        name = os.path.basename(name) if name else self._manager.app_name

        if self._find_item_in_list(favorites, name):
            return

        url = CFURLCreateWithString(
            None, 'file://{}'.format(urllib2.quote(folder_path)), None)
        if not url:
            log.warning(
                'Could not generate valid favorite URL for: %r', folder_path)
            return

        # Register the folder as favorite if not already there
        item = LSSharedFileListInsertItemURL(
            favorites, kLSSharedFileListItemBeforeFirst,
            name, None, url, {}, [])
        if item:
            log.debug('Registered new favorite in Finder for: %r', folder_path)

    def unregister_folder_link(self, name=None):
        from LaunchServices import LSSharedFileListItemRemove

        favorites = self._get_favorite_list()
        if not favorites:
            log.warning('Could not fetch the Finder favorite list.')
            return

        name = os.path.basename(name) if name else self._manager.app_name

        item = self._find_item_in_list(favorites, name)
        if not item:
            return

        LSSharedFileListItemRemove(favorites, item)

    @staticmethod
    def _get_favorite_list():
        from LaunchServices import LSSharedFileListCreate
        from LaunchServices import kLSSharedFileListFavoriteItems

        return LSSharedFileListCreate(
            None, kLSSharedFileListFavoriteItems, None)

    @staticmethod
    def _find_item_in_list(lst, name):
        from LaunchServices import LSSharedFileListCopySnapshot
        from LaunchServices import LSSharedFileListItemCopyDisplayName

        for item in LSSharedFileListCopySnapshot(lst, None)[0]:
            item_name = LSSharedFileListItemCopyDisplayName(item)
            if name == item_name:
                return item
        return None
