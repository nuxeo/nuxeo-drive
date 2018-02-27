# coding: utf-8
import os
import urllib2
from logging import getLogger

from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import normalized_path

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

    def _get_agent_file(self):
        agents_folder = os.path.expanduser('~/Library/LaunchAgents')
        agent_filepath = os.path.join(
            agents_folder, self._manager.get_cf_bundle_identifier() + '.plist')
        return agent_filepath

    def register_startup(self):
        """Register the Nuxeo Drive.app as a user Launch Agent

        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
        """
        agent_filepath = self._get_agent_file()
        agents_folder = os.path.dirname(agent_filepath)
        exe_path = self._manager.find_exe_path()
        log.debug('Registering "%s" for startup in: %s',
                  exe_path, agent_filepath)

        if not os.path.exists(agents_folder):
            log.debug('Making launch agent folder %s', agents_folder)
            os.makedirs(agents_folder)

        log.debug('Writing launch agent file %s', agent_filepath)
        with open(agent_filepath, 'wb') as f:
            f.write(self.NDRIVE_AGENT_TEMPLATE % exe_path)

    def unregister_startup(self):
        agent_filepath = self._get_agent_file()
        if os.path.exists(agent_filepath):
            os.remove(agent_filepath)

    def register_contextual_menu(self):
        # Handled through the FinderSync extension
        pass

    def unregister_contextual_menu(self):
        # Handled through the FinderSync extension
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
