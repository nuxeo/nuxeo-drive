import os
import sys
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path
from nxdrive.utils import update_win32_reg_key

log = get_logger(__name__)

def register_startup():
    if sys.platform == 'win32':
        register_startup_win32()
    elif sys.platform == 'darwin':
        register_startup_darwin()


def register_startup_win32():
    """Register ndrive as a startup application in the Registry"""
    import _winreg

    reg_key = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    app_name = 'Nuxeo Drive'
    exe_path = find_exe_path()
    if exe_path is None:
        log.warning('Not a frozen windows exe: '
                 'skipping startup application registration')
        return

    log.debug("Registering '%s' application %s to registry key %s",
        app_name, exe_path, reg_key)
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    update_win32_reg_key(
        reg, reg_key,
        [(app_name, _winreg.REG_SZ, exe_path)],
    )


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


def register_startup_darwin():
    """Register the Nuxeo Drive.app as a user Launch Agent

    http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html

    """
    agents_folder = os.path.expanduser('~/Library/LaunchAgents')
    agent_filepath = os.path.join(agents_folder, NDRIVE_AGENT_FILENAME)
    exe_path = find_exe_path()
    log.debug("Registering '%s' for startup in: '%s'", exe_path, agent_filepath)

    if not os.path.exists(agents_folder):
        os.makedirs(agents_folder)

    with open(agent_filepath, 'wb') as f:
        f.write(NDRIVE_AGENT_TEMPLATE % exe_path)
