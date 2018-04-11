# coding: utf-8
import os
import stat
import sys
import urllib2
from logging import getLogger

from .. import AbstractOSIntegration
from ...constants import BUNDLE_IDENTIFIER
from ...utils import normalized_path, force_decode

log = getLogger(__name__)


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

    def __init__(self, manager):
        super(DarwinIntegration, self).__init__(manager)
        log.debug('Telling plugInKit to use the FinderSync')
        os.system('pluginkit -e use -i {}.NuxeoFinderSync'.format(
            BUNDLE_IDENTIFIER))

    def _cleanup(self):
        log.debug('Telling plugInKit to ignore the FinderSync')
        os.system('pluginkit -e ignore -i {}.NuxeoFinderSync'.format(
            BUNDLE_IDENTIFIER))

    def _get_agent_file(self):
        return os.path.join(
            os.path.expanduser('~/Library/LaunchAgents'),
            '{}.plist'.format(BUNDLE_IDENTIFIER))

    def register_startup(self):
        """
        Register the Nuxeo Drive.app as a user Launch Agent.
        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
        """
        agent = os.path.join(
            os.path.expanduser('~/Library/LaunchAgents'),
            '{}.plist'.format(BUNDLE_IDENTIFIER))
        if os.path.isfile(agent):
            return

        agents_folder = os.path.dirname(agent)
        if not os.path.exists(agents_folder):
            log.debug('Making launch agent folder %r', agents_folder)
            os.makedirs(agents_folder)

        exe = os.path.realpath(sys.executable)
        log.debug('Registering %r for startup in %r', exe, agent)
        with open(agent, 'wb') as f:
            f.write(self.NDRIVE_AGENT_TEMPLATE % exe)

    def unregister_startup(self):
        agent = self._get_agent_file()
        if os.path.isfile(agent):
            log.debug('Unregistering startup agent %r', agent)
            os.remove(agent)

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

    def _send_notification(self, name, content):
        """
        Send a notification through the macOS notification center
        to the FinderSync app extension.

        :param name: name of the notification
        :param content: content to send
        """
        from Foundation import NSDistributedNotificationCenter
        nc = NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_userInfo_(name, None, content)

    def _set_monitoring(self, operation, path):
        """
        Set the monitoring of a folder by the FinderSync.

        :param operation: 'watch' or 'unwatch'
        :param path: path to the folder
        """
        name = '{}.watchFolder'.format(BUNDLE_IDENTIFIER)
        self._send_notification(name, {'operation': operation, 'path': path})

    def watch_folder(self, folder):
        log.debug('FinderSync now watching %r', folder)
        self._set_monitoring('watch', folder)

    def unwatch_folder(self, folder):
        log.debug('FinderSync now ignoring %r', folder)
        self._set_monitoring('unwatch', folder)

    def send_sync_status(self, state, path):
        """
        Send the sync status of a file to the FinderSync.

        :param state: current local state of the file
        :param path: full path of the file
        """
        try:
            path = force_decode(path)
            if not os.path.exists(path):
                return

            name = '{}.syncStatus'.format(BUNDLE_IDENTIFIER)
            status = 'unsynced'

            readonly = (os.stat(path).st_mode
                        & (stat.S_IWUSR | stat.S_IWGRP)) == 0
            if readonly:
                status = 'locked'
            elif state:
                if state.error_count > 0:
                    status = 'error'
                elif state.pair_state == 'conflicted':
                    status = 'conflicted'
                elif state.local_state == 'synchronized':
                    status = 'synced'
                elif state.pair_state == 'unsynchronized':
                    status = 'unsynced'
                elif state.processor != 0:
                    status = 'syncing'

            log.trace('Sending status %r for file %r to FinderSync',
                      status, path)
            self._send_notification(name, {'status': status, 'path': path})
        except:
            log.exception('Error while trying to send status to FinderSync')

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
