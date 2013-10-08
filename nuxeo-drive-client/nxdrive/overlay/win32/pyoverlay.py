from win32com.shell import shell, shellcon
import winerror
import urllib
import subprocess

driveRoots = []
currentFolderUri = None
syncStatuses = None


def nxlog(msg):
    logFile = open("C:\\driveOverlay.log", "a")
    logFile.write(msg + "\n")
    logFile.close()


def drive_exec(cmds):
    # add the ndrive command !
    cmds.insert(0, "ndrive")
    nxlog("Executing ndrive command: " + str(cmds))
    p = subprocess.Popen(cmds, stdout=subprocess.PIPE)
    result, _ = p.communicate()
    nxlog("Result = " + result)
    return eval(result)


def get_drive_roots():
    if (len(driveRoots) == 0):
        nxlog("Getting Nuxeo Drive local folders")
        driveRoots = [urllib.quote(x) for x in drive_exec(['local_folders', ])]
    return driveRoots


class IconOverlay:

    _reg_clsid_ = '{B4123171-F6D6-4FAD-9402-8F6B04E439C7}'
    _reg_progid_ = 'NuxeoDrive.PythonOverlayHandler'
    _reg_desc_ = 'Icon Overlay Handler for Nuxeo Drive'
    _public_methods_ = ['GetOverlayInfo', 'GetPriority', 'IsMemberOf']
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]

    def __init__(self):
        nxlog("Starting")

    def get_overlay_info(self):
        nxlog("return Normal icon")
        return (r'C:\Drive\NormalIcon.ico', 0, shellcon.ISIOI_ICONFILE)

    def get_priority(self):
        return 50

    def IsMemberOf(self, fname, attributes):
        nxlog("calling isMember on " + fname)
        if ("nuxeo" in fname):
            if ("finan" in fname):
                return winerror.S_FALSE
            else:
                nxlog("return ok for synced")
                return winerror.S_OK
        return winerror.S_FALSE


class PendingIconOverlay:

    _reg_clsid_ = '{BE8CEBD1-5AB8-403F-9984-F34251A1705C}'
    _reg_progid_ = 'NuxeoDrive.PythonPendingOverlayHandler'
    _reg_desc_ = 'Icon Overlay Handler for Nuxeo Drive Pending files'
    _public_methods_ = ['GetOverlayInfo', 'GetPriority', 'IsMemberOf']
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]

    def __init__(self):
        nxlog("Starting")

    def GetOverlayInfo(self):
        nxlog("return Modified icon")
        return (r'C:\Drive\ModifiedIcon.ico', 0, shellcon.ISIOI_ICONFILE)

    def GetPriority(self):
        return 50

    def IsMemberOf(self, fname, attributes):
        nxlog("calling isMember on " + fname)
        if ("nuxeo" in fname):
            if ("finan" in fname):
                nxlog("return ok for pending")
                return winerror.S_OK
            else:
                return winerror.S_FALSE
        return winerror.S_FALSE


if __name__ == '__main__':
    import win32api
    import win32con
    import win32com.server.register

    win32com.server.register.UseCommandLine(IconOverlay)
    keyname = r'Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\NuxeoDriveOverlay'
    key = win32api.RegCreateKey(win32con.HKEY_LOCAL_MACHINE, keyname)
    win32api.RegSetValue(key, None, win32con.REG_SZ, IconOverlay._reg_clsid_)

    win32com.server.register.UseCommandLine(PendingIconOverlay)
    keyname = r'Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\NuxeoDrivePendingOverlay'
    key = win32api.RegCreateKey(win32con.HKEY_LOCAL_MACHINE, keyname)
    win32api.RegSetValue(key, None, win32con.REG_SZ,
                         PendingIconOverlay._reg_clsid_)
