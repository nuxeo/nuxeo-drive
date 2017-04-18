# coding: utf-8
""" Based on code from
    https://code.google.com/p/winsys/source/browse/trunk/random/file_handles.py
"""

import os
import struct
import threading
from ctypes import *
from ctypes.wintypes import *
from time import sleep

import ntsecuritycon
import win32api
import win32con
import win32file
import win32security
import winerror

from nxdrive.logging_config import get_logger

UCHAR = c_ubyte
PVOID = c_void_p
ntdll = windll.ntdll

SystemHandleInformation = 16
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
STATUS_BUFFER_OVERFLOW = 0x80000005L
STATUS_INVALID_HANDLE = 0xC0000008L
STATUS_BUFFER_TOO_SMALL = 0xC0000023L
STATUS_SUCCESS = 0

CURRENT_PROCESS = win32api.GetCurrentProcess ()

threads = 0
log = get_logger(__name__)


class x_file_handles(Exception):
    pass


def signed_to_unsigned(signed):
    unsigned, = struct.unpack("L", struct.pack("l", signed))
    return unsigned


class SYSTEM_HANDLE_TABLE_ENTRY_INFO(Structure):
    _fields_ = [
        ("UniqueProcessId", USHORT),
        ("CreatorBackTraceIndex", USHORT),
        ("ObjectTypeIndex", UCHAR),
        ("HandleAttributes", UCHAR),
        ("HandleValue", USHORT),
        ("Object", PVOID),
        ("GrantedAccess", ULONG),
    ]


class SYSTEM_HANDLE_INFORMATION(Structure):
    _fields_ = [
        ("NumberOfHandles", ULONG),
        ("Handles", SYSTEM_HANDLE_TABLE_ENTRY_INFO * 1),
    ]


class LSA_UNICODE_STRING(Structure):
    _fields_ = [
        ("Length", USHORT),
        ("MaximumLength", USHORT),
        ("Buffer", LPWSTR),
    ]


class PUBLIC_OBJECT_TYPE_INFORMATION(Structure):
    _fields_ = [
        ("Name", LSA_UNICODE_STRING),
        ("Reserved", ULONG * 22),
    ]


class OBJECT_NAME_INFORMATION(Structure):
    _fields_ = [
        ("Name", LSA_UNICODE_STRING),
    ]


class IO_STATUS_BLOCK_UNION(Union):
    _fields_ = [
        ("Status", LONG),
        ("Pointer", PVOID),
    ]


class IO_STATUS_BLOCK(Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("u", IO_STATUS_BLOCK_UNION),
        ("Information", POINTER(ULONG)),
    ]


class FILE_NAME_INFORMATION(Structure):
    filename_size = 4096
    _fields_ = [
        ("FilenameLength", ULONG),
        ("FileName", WCHAR * filename_size),
    ]


class GetObjectInfoThread(threading.Thread):
    def __init__(self, pid, handles, filter_type):
        super(GetObjectInfoThread, self).__init__(target=self._get_object_info, args=(self, pid, handles, filter_type))
        self._pid = pid
        self._handles = handles
        self._filter_type = filter_type
        self._result = []
        self.lastGrantedAccess = None

    def get_pid(self):
        return self._pid

    @staticmethod
    def get_type_info(handle):
        public_object_type_information = PUBLIC_OBJECT_TYPE_INFORMATION()
        size = DWORD(sizeof(public_object_type_information))
        while True:
            result = signed_to_unsigned(
                ntdll.NtQueryObject(handle, 2, byref(public_object_type_information), size, None)
            )
            if result == STATUS_SUCCESS:
                return public_object_type_information.Name.Buffer
            elif result == STATUS_INFO_LENGTH_MISMATCH:
                size = DWORD(size.value * 4)
                resize(public_object_type_information, size.value)
            elif result == STATUS_INVALID_HANDLE:
                return None
            elif result == 0xc0000005:
                # Access denied
                # Windows 10 result
                return None
            raise x_file_handles ("NtQueryObject.2", hex (result))

    @staticmethod
    def get_name_info(handle):
        object_name_information = OBJECT_NAME_INFORMATION ()
        size = DWORD(sizeof(object_name_information))
        while True:
            info = ntdll.NtQueryObject(
                    handle, 1, byref(object_name_information), size, None
                )
            result = signed_to_unsigned(
                info
            )
            if result == STATUS_SUCCESS:
                return object_name_information.Name.Buffer
            elif result in (STATUS_BUFFER_OVERFLOW, STATUS_BUFFER_TOO_SMALL, STATUS_INFO_LENGTH_MISMATCH):
                size = DWORD(size.value * 4)
                resize(object_name_information, size.value)

    @staticmethod
    def get_object_info(pid, process_handle, handle, filter_type):
        type_ = GetObjectInfoThread.get_type_info(handle)
        if filter_type is not None and filter_type != type_ and type_ is not None:
            return
        name = GetObjectInfoThread.get_name_info(handle)
        if name:
            return pid, type, name, handle

    @staticmethod
    def _get_object_info(obj, pid, handles, filter_type):
        try:
            process_handler = win32api.OpenProcess(win32con.PROCESS_DUP_HANDLE, 0, pid)
        except win32api.error:
            return
        for handle_obj in handles:
            obj.lastGrantedAccess = handle_obj[1]
            handle = handle_obj[0]
            hDuplicate = WindowsProcessFileHandlerSniffer.get_process_handle(process_handler, handle)
            if hDuplicate is None:
                continue
            handle = int(hDuplicate)
            resource = GetObjectInfoThread.get_object_info(pid, process_handler, handle, filter_type)
            win32api.CloseHandle(hDuplicate)
            if resource is not None:
                obj._result.append(resource)
        win32api.CloseHandle(process_handler)

    def get_results(self):
        return self._result


class WindowsProcessFileHandlerSniffer():

    def __init__(self):
        self.DEVICE_DRIVES = dict()
        self._running = False
        self._threads = []
        self._pid_blacklist = dict()
        self._pid_blacklist[os.getpid()] = True
        # Get Windows Drive
        for d in "abcdefghijklmnopqrstuvwxyz":
            try:
                device = win32file.QueryDosDevice(d + ":").strip("\x00").lower()
                self.DEVICE_DRIVES[device] = d.upper() + ":"
            except win32file.error, (errno, errctx, errmsg):
                if errno != 2:
                    raise
        self._increase_privileges()

    @staticmethod
    def get_process_handle(hProcess, handle):
        try:
            return win32api.DuplicateHandle(hProcess, handle, CURRENT_PROCESS,
                                            0, 0, win32con.DUPLICATE_SAME_ACCESS)
        except win32api.error, (errno, errctx, errmsg):
            if errno not in (winerror.ERROR_ACCESS_DENIED,
                             winerror.ERROR_INVALID_PARAMETER,
                             winerror.ERROR_INVALID_HANDLE,
                             winerror.ERROR_NOT_SUPPORTED):
                raise
            return None

    @staticmethod
    def get_handles():
        system_handle_information = SYSTEM_HANDLE_INFORMATION ()
        size = DWORD(sizeof(system_handle_information))
        while True:
            result = signed_to_unsigned(ntdll.NtQuerySystemInformation(
                SystemHandleInformation, byref(system_handle_information),
                size, byref(size)))
            if result == STATUS_SUCCESS:
                break
            elif result == STATUS_INFO_LENGTH_MISMATCH:
                size = DWORD(size.value * 4)
                resize(system_handle_information, size.value)
            else:
                raise x_file_handles("NtQuerySystemInformation", hex(result))

        result = dict()
        pHandles = cast(system_handle_information.Handles,
            POINTER(SYSTEM_HANDLE_TABLE_ENTRY_INFO
                    * system_handle_information.NumberOfHandles))
        for handle in pHandles.contents:
            if handle.UniqueProcessId not in result:
                result[handle.UniqueProcessId] = dict()
                result[handle.UniqueProcessId]["handles"] = []
                result[handle.UniqueProcessId]["risky_handles"] = []

            # Useless for now but keep for later use in case
            if handle.GrantedAccess in (0x1a0089, 0x1a019f, 0x12019f, 0x120189,
                                        0x01f01ff, 0x100081):
                # Some process like ssh-agent or chrome make NtQueryObject hang
                # when queried
                result[handle.UniqueProcessId]["risky_handles"].append(
                    (handle.HandleValue, handle.GrantedAccess))
                continue

            result[handle.UniqueProcessId]["risky_handles"].append(
                (handle.HandleValue, handle.GrantedAccess))
        return result

    def get_main_open_files(self, pids=None, filter_type='File'):
        handles = self.get_handles()
        info_threads = []
        # Remove stopped pids from blacklist
        remove_pids = []
        for pid in self._pid_blacklist:
            if pid not in handles:
                remove_pids.append(pid)
        for pid in remove_pids:
            del self._pid_blacklist[pid]

        # Go through handles ( stored by pid )
        for pid in handles:
            if pid in self._pid_blacklist:
                continue
            try:
                process_handler = win32api.OpenProcess(win32con.PROCESS_DUP_HANDLE, 0, pid)
            except win32api.error:
                continue
            for handle_obj in handles[pid]['handles']:
                handle = handle_obj[0]
                hDuplicate = WindowsProcessFileHandlerSniffer.get_process_handle(process_handler, handle)
                if hDuplicate is None:
                    continue
                handle = int(hDuplicate)
                resource = GetObjectInfoThread.get_object_info(pid, process_handler, handle, filter_type)
                win32api.CloseHandle(hDuplicate)
                if resource is not None:
                    yield resource
            win32api.CloseHandle(process_handler)
            if len(handles[pid]['risky_handles']) > 0:
                # As they can hang the kernel we need to launch another thread for those one
                thread = GetObjectInfoThread(pid, handles[pid]['risky_handles'], filter_type)
                # To avoid crash at the end
                thread.setDaemon(True)
                thread.start()
                info_threads.append(thread)
        # Wait 2s
        sleep(2)
        # Go through all the remaining thread
        for thread in info_threads:
            if thread.is_alive():
                # Should not be blacklist the pid
                self._pid_blacklist[thread.get_pid()] = True
                log.trace('Blacklisting process %d because of stuck thread (GrantedAccess: %d)',
                          thread.get_pid(), thread.lastGrantedAccess)
            else:
                for result in thread.get_results():
                    yield result

    def filepath_from_devicepath(self, devicepath):
        if devicepath is None:
            return None
        devicepath_lower = devicepath.lower()
        for device, drive in self.DEVICE_DRIVES.items():
            if devicepath_lower.startswith(device):
                return drive + devicepath[len(device):]
        return devicepath

    @staticmethod
    def _increase_privileges():
        win32security.LookupPrivilegeValue(u"", win32security.SE_DEBUG_NAME)
        win32security.OpenProcessToken(CURRENT_PROCESS, ntsecuritycon.MAXIMUM_ALLOWED)

    def get_open_files(self, pids=None):
        if self._running:
            raise Exception("Can't multithread open_files")
        try:
            self._running = True
            for file in self.get_main_open_files(pids):
                path = self.filepath_from_devicepath(file[2])
                if path is None or not os.path.exists(path) or os.path.isdir(path):
                    continue
                yield (file[0], path, file[1], file[3])
        except x_file_handles, (context, errno):
            log.trace("Error in %r - with errno : %d", context, errno)
        finally:
            self._running = False
