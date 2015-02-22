'''
@author: Remi Cattiau
'''
from nxdrive.osi import AbstractOSIntegration
import os
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path

log = get_logger(__name__)


class DarwinIntegration(AbstractOSIntegration):
    '''
    classdocs
    '''
    NXDRIVE_SCHEME = 'nxdrive'
    NDRIVE_AGENT_FILENAME = "org.nuxeo.drive.plist"
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
        agent_filepath = os.path.join(agents_folder, self.NDRIVE_AGENT_FILENAME)
        return agent_filepath

    def register_startup(self):
        """Register the Nuxeo Drive.app as a user Launch Agent

        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html

        """
        agent_filepath = self._get_agent_file()
        agents_folder = os.path.dirname(agent_filepath)
        exe_path = find_exe_path()
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
        """Register the URL scheme listener using PyObjC"""
        log.warning("Cannot unregister %r scheme: not implemented", self.NXDRIVE_SCHEME)
