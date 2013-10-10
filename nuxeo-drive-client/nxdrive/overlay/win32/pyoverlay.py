from win32com.shell import shell, shellcon
import pythoncom
import winerror
import urllib
import subprocess
import os

driveRoots = []
currentFolderUri = None
syncStatuses = None


def nxlog(msg):
    logFile = open("C:\\Users\\nuxeo\\driveOverlay.log", "a")
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
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier, pythoncom.IID_IDispatch]

    def __init__(self):
        nxlog("Starting")

    def GetOverlayInfo(self):
        nxlog("return Normal icon")
        icon_path = os.path.abspath(r'C:\Users\nuxeo\Desktop\nuxeo-drive\nuxeo-drive-client\nxdrive\data\icons\overlay\win32\NormalIcon.ico')
        nxlog("iconpath = " + icon_path)
        f = open(icon_path, 'r')
        nxlog("file opened")
        f.close()
        nxlog("file closed")
        return (icon_path, 0, shellcon.ISIOI_ICONFILE)

    def GetPriority(self):
        nxlog("calling IconOverlay.GetPriority")
        return 0

    def IsMemberOf(self, fname, attributes):
        nxlog("calling isMember on " + fname)
        if ("Nuxeo" in fname):
            if ("finan" in fname):
                return winerror.E_FAIL
            else:
                nxlog("return ok for synced")
                return winerror.S_OK
        return winerror.E_FAIL


class PendingIconOverlay:

    _reg_clsid_ = '{BE8CEBD1-5AB8-403F-9984-F34251A1705C}'
    _reg_progid_ = 'NuxeoDrive.PythonPendingOverlayHandler'
    _reg_desc_ = 'Icon Overlay Handler for Nuxeo Drive Pending files'
    _public_methods_ = ['GetOverlayInfo', 'GetPriority', 'IsMemberOf']
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier, pythoncom.IID_IDispatch]

    def __init__(self):
        nxlog("Starting")

    def GetOverlayInfo(self):
        nxlog("return Modified icon")
        icon_path = os.path.abspath(r'C:\Users\nuxeo\Desktop\nuxeo-drive\nuxeo-drive-client\nxdrive\data\icons\overlay\win32\ModifiedIcon.ico')
        nxlog("iconpath = " + icon_path)
        f = open(icon_path, 'r')
        nxlog("file opened")
        f.close()
        nxlog("file closed")
        return (icon_path, 0, shellcon.ISIOI_ICONFILE)		

    def GetPriority(self):
        nxlog("calling PendingIconOverlay.GetPriority")
        return 0

    def IsMemberOf(self, fname, attributes):
        nxlog("calling isMember on " + fname)
        if ("Nuxeo" in fname):
            if ("finan" in fname):
                nxlog("return ok for pending")
                return winerror.S_OK
            else:
                return winerror.E_FAIL
        return winerror.E_FAIL


# if __name__ == '__main__':
    # import win32api
    # import win32con
    # import win32com.server.register

    # win32com.server.register.UseCommandLine(IconOverlay)
    # keyname = r'Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\NuxeoDriveOverlay'
    # key = win32api.RegCreateKey(win32con.HKEY_LOCAL_MACHINE, keyname)
    # win32api.RegSetValue(key, None, win32con.REG_SZ, IconOverlay._reg_clsid_)

    # win32com.server.register.UseCommandLine(PendingIconOverlay)
    # keyname = r'Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\NuxeoDrivePendingOverlay'
    # key = win32api.RegCreateKey(win32con.HKEY_LOCAL_MACHINE, keyname)
    # win32api.RegSetValue(key, None, win32con.REG_SZ,
                         # PendingIconOverlay._reg_clsid_)

REG_PATH =r'Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers'
REG_KEY = "NuxeoDriveOverlay"
REG_KEY2 = "NuxeoDrivePendingOverlay"
						 
def DllRegisterServer():
    print "Registering %s" % REG_KEY
    import _winreg

    key = _winreg.CreateKey(_winreg.HKEY_LOCAL_MACHINE, REG_PATH)
    subkey = _winreg.CreateKey(key, IconOverlay._reg_progid_)
    _winreg.SetValueEx(subkey, None, 0, _winreg.REG_SZ, IconOverlay._reg_clsid_)
    print "Registration complete: %s" % IconOverlay._reg_desc_

def DllUnregisterServer():
    print "Unregistering %s" % REG_KEY
    import _winreg
    try:
        key = _winreg.DeleteKey(_winreg.HKEY_LOCAL_MACHINE, r"%s\%s" % (REG_PATH, IconOverlay._reg_progid_))
    except WindowsError, details:
        import errno
        if details.errno != errno.ENOENT:
            raise
    print "Unregistration complete: %s" % IconOverlay._reg_desc_

def DllRegisterServer2():
    print "Registering %s" % REG_KEY2
    import _winreg

    key = _winreg.CreateKey(_winreg.HKEY_LOCAL_MACHINE, REG_PATH)
    subkey = _winreg.CreateKey(key, PendingIconOverlay._reg_progid_)
    _winreg.SetValueEx(subkey, None, 0, _winreg.REG_SZ, PendingIconOverlay._reg_clsid_)
    print "Registration complete: %s" % PendingIconOverlay._reg_desc_

def DllUnregisterServer2():
    print "Unregistering %s" % REG_KEY2
    import _winreg
    try:        
		key = _winreg.DeleteKey(_winreg.HKEY_LOCAL_MACHINE, r"%s\%s" % (REG_PATH, PendingIconOverlay._reg_progid_))
    except WindowsError, details:
        import errno
        if details.errno != errno.ENOENT:
            raise
    print "Unregistration complete: %s" % PendingIconOverlay._reg_desc_
	
if __name__=='__main__':
    from win32com.server import register
    register.UseCommandLine(IconOverlay,
                            finalize_register = DllRegisterServer,
                            finalize_unregister = DllUnregisterServer)
    register.UseCommandLine(PendingIconOverlay,
                            finalize_register = DllRegisterServer2,
                            finalize_unregister = DllUnregisterServer2)
