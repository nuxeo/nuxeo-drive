# coding: utf-8
import os
import urllib2

import AppKit
import objc
from AppKit import NSRegisterServicesProvider, NSURLPboardType
from Foundation import NSObject, NSURL

from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import normalized_path

log = get_logger(__name__)


def serviceSelector(fn):
    # this is the signature of service selectors
    return objc.selector(fn, signature="v@:@@o^@")


class RightClickService(NSObject):

    @serviceSelector
    def macRightClick_userData_error_(self, pboard, data, error):
        log.trace("macRightClick has been called")
        try:
            types = pboard.types()
            if NSURLPboardType in types:
                pboardArray = pboard.propertyListForType_(NSURLPboardType)
                log.error("Retrieve property list stuff %r", pboardArray)
                for value in pboardArray:
                    if value is None or value == "":
                        continue
                    # TODO Replug prompt_metadata on this one
                    url = NSURL.URLWithString_(value)
                    if url is None:
                        if value.startswith("file://"):
                            value = value[7:]
                        value = urllib2.unquote(value)
                    else:
                        value = url.path()
                    log.debug("Should open : %s", value)
                    from PyQt4.QtCore import QCoreApplication
                    QCoreApplication.instance().show_metadata(value)
        except:
            log.exception('Right click service error')


class DarwinIntegration(AbstractOSIntegration):
    NXDRIVE_SCHEME = 'nxdrive'
    NDRIVE_AGENT_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.nuxeo.drive.agentlauncher</string>
  <key>RunAtLoad</key>
  <true/>
  <key>Program</key>
  <string>%s</string>
</dict>
</plist>
    """

    def _get_agent_file(self):
        agents_folder = os.path.expanduser('~/Library/LaunchAgents')
        agent_filepath = os.path.join(agents_folder, self._manager.get_cf_bundle_identifier() + '.plist')
        return agent_filepath

    def register_startup(self):
        """Register the Nuxeo Drive.app as a user Launch Agent

        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html

        """
        agent_filepath = self._get_agent_file()
        agents_folder = os.path.dirname(agent_filepath)
        exe_path = self._manager.find_exe_path()
        log.debug("Registering '%s' for startup in: '%s'",
                  exe_path, agent_filepath)

        if not os.path.exists(agents_folder):
            log.debug("Making launch agent folder %s", agents_folder)
            os.makedirs(agents_folder)

        log.debug("Writing launch agent file %s", agent_filepath)
        with open(agent_filepath, 'wb') as f:
            f.write(self.NDRIVE_AGENT_TEMPLATE % exe_path)

    def unregister_startup(self):
        agent_filepath = self._get_agent_file()
        if os.path.exists(agent_filepath):
            os.remove(agent_filepath)

    def _register_services(self):
        serviceProvider = RightClickService.alloc().init()
        NSRegisterServicesProvider(serviceProvider, self._manager.app_name)
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
        try:
            from Foundation import NSBundle
            from LaunchServices import LSSetDefaultHandlerForURLScheme
        except ImportError:
            log.warning("Cannot register %r scheme: missing OSX Foundation module",
                        self.NXDRIVE_SCHEME)
            return

        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if bundle_id == 'org.python.python':
            log.debug("Skipping URL scheme registration as this program "
                      " was launched from the Python OSX app bundle")
            return
        LSSetDefaultHandlerForURLScheme(self.NXDRIVE_SCHEME, bundle_id)
        log.debug("Registered bundle '%s' for URL scheme '%s'", bundle_id,
                  self.NXDRIVE_SCHEME)

    def unregister_protocol_handlers(self):
        # Dont unregister, should be removed when Bundle removed
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
        try:
            from LaunchServices import LSSharedFileListInsertItemURL
            from LaunchServices import kLSSharedFileListItemBeforeFirst
            from LaunchServices import CFURLCreateWithString
        except ImportError:
            log.warning("PyObjC package is not installed:"
                        " skipping favorite link creation")
            return
        folder_path = normalized_path(folder_path)
        if name is None:
            name = self._manager.app_name

        lst = self._get_favorite_list()
        if lst is None:
            log.warning("Could not fetch the Finder favorite list.")
            return

        url = CFURLCreateWithString(None, 'file://'
                                    + urllib2.quote(folder_path), None)
        if url is None:
            log.warning('Could not generate valid favorite URL for: %s',
                        folder_path)
            return

        # Register the folder as favorite if not already there
        item = LSSharedFileListInsertItemURL(
            lst, kLSSharedFileListItemBeforeFirst, name, None, url,
            {}, [])
        if item is not None:
            log.debug("Registered new favorite in Finder for: %s", folder_path)

    def unregister_folder_link(self, name):
        try:
            from LaunchServices import LSSharedFileListItemRemove
        except ImportError:
            log.warning("PyObjC package is not installed:"
                        " skipping favorite link creation")
            return

        if name is None:
            name = self._manager.app_name

        lst = self._get_favorite_list()
        if lst is None:
            log.warning("Could not fetch the Finder favorite list.")
            return

        item = self._find_item_in_list(lst, name)
        if item is None:
            log.warning("Unable to find the favorite list item")
            return

        LSSharedFileListItemRemove(lst, item)

    @staticmethod
    def _get_favorite_list():
        from LaunchServices import LSSharedFileListCreate
        from LaunchServices import kLSSharedFileListFavoriteItems

        return LSSharedFileListCreate(None,
                                      kLSSharedFileListFavoriteItems,
                                      None)

    @staticmethod
    def _find_item_in_list(lst, name):
        from LaunchServices import LSSharedFileListCopySnapshot
        from LaunchServices import LSSharedFileListItemCopyDisplayName

        for item in LSSharedFileListCopySnapshot(lst, None)[0]:
            if name == LSSharedFileListItemCopyDisplayName(item):
                return item
        return None
