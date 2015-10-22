__author__ = 'loopingz'

# Based on https://code.google.com/p/winsys/source/browse/trunk/random/file_handles.py code

import os, sys
from ctypes import *
from ctypes.wintypes import *
import Queue
import re
import struct
import threading

import ntsecuritycon
import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32security
import winerror

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
DEVICE_DRIVES = {}
for d in "abcdefghijklmnopqrstuvwxyz":
    try:
        DEVICE_DRIVES[win32file.QueryDosDevice (d + ":").strip ("\x00").lower ()] = d + ":"
    except win32file.error, (errno, errctx, errmsg):
        if errno == 2:
            pass
        else:
            raise


class x_file_handles(Exception):
    pass


def signed_to_unsigned (signed):
    unsigned, = struct.unpack ("L", struct.pack ("l", signed))
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


def get_handles():
    system_handle_information = SYSTEM_HANDLE_INFORMATION ()
    size = DWORD (sizeof (system_handle_information))
    while True:
        result = ntdll.ZwQuerySystemInformation (
            SystemHandleInformation,
            byref (system_handle_information),
            size,
            byref (size)
        )
        result = signed_to_unsigned (result)
        if result == STATUS_SUCCESS:
            break
        elif result == STATUS_INFO_LENGTH_MISMATCH:
            size = DWORD (size.value * 4)
            resize (system_handle_information, size.value)
        else:
            raise x_file_handles ("ZwQuerySystemInformation", hex (result))

    pHandles = cast (
        system_handle_information.Handles,
        POINTER (SYSTEM_HANDLE_TABLE_ENTRY_INFO * system_handle_information.NumberOfHandles)
    )
    for handle in pHandles.contents:
        yield handle.UniqueProcessId, handle.HandleValue


def get_process_handle(pid, handle):
    try:
        hProcess = win32api.OpenProcess (win32con.PROCESS_DUP_HANDLE, 0, pid)
        return win32api.DuplicateHandle (hProcess, handle, CURRENT_PROCESS, 0, 0, win32con.DUPLICATE_SAME_ACCESS)
    except win32api.error, (errno, errctx, errmsg):
        if errno in (
            winerror.ERROR_ACCESS_DENIED,
            winerror.ERROR_INVALID_PARAMETER,
            winerror.ERROR_INVALID_HANDLE,
            winerror.ERROR_NOT_SUPPORTED
        ):
            return None
        else:
            raise


def get_type_info(handle):
    public_object_type_information = PUBLIC_OBJECT_TYPE_INFORMATION ()
    size = DWORD(sizeof(public_object_type_information))
    while True:
        result = signed_to_unsigned(
            ntdll.ZwQueryObject(
            handle, 2, byref(public_object_type_information), size, None
            )
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
        else:
            raise x_file_handles ("ZwQueryObject.2", hex (result))


def get_name_info(handle):
    object_name_information = OBJECT_NAME_INFORMATION ()
    size = DWORD (sizeof (object_name_information))
    while True:
        result = signed_to_unsigned (
            ntdll.ZwQueryObject (
            handle, 1, byref (object_name_information), size, None
            )
        )
        if result == STATUS_SUCCESS:
            return object_name_information.Name.Buffer
        elif result in (STATUS_BUFFER_OVERFLOW, STATUS_BUFFER_TOO_SMALL, STATUS_INFO_LENGTH_MISMATCH):
            size = DWORD(size.value * 4)
            resize(object_name_information, size.value)
        else:
            return None


def can_access(handle):
    try:
        return win32event.WaitForSingleObject (handle, 10) not in (win32event.WAIT_TIMEOUT, win32event.WAIT_ABANDONED)
    except win32event.error, (errno, errctx, errmsg):
        if errno in (winerror.ERROR_ACCESS_DENIED,):
            return False
        else:
            raise


def get_object_info(requests, results, filter_type='File'):
    while True:
        pid, handle = requests.get ()
        type = get_type_info(handle)
        if filter_type is not None and (filter_type == type or type is None):
            continue
        name = get_name_info(handle)
        if (name is None and type is None):
            # Not enought info to add to result
            continue
        results.put((pid, type, name))


def get_main_open_files():
    requests = Queue.Queue()
    results = Queue.Queue()

    # Launch 20 threads to get the result
    for i in range(20):
        t = threading.Thread(target=get_object_info, args=(requests, results))
        t.setDaemon(True)
        t.start()

    public_object_type_information = PUBLIC_OBJECT_TYPE_INFORMATION ()
    object_name_information = OBJECT_NAME_INFORMATION ()
    this_pid = os.getpid()

    for pid, handle in get_handles():
        if pid == this_pid:
            continue
        hDuplicate = get_process_handle(pid, handle)
        if hDuplicate is None:
            continue
        else:
            requests.put((pid, int(hDuplicate)))

    while True:
        try:
            yield results.get(True, 2)
        except Queue.Empty:
            break


def filepath_from_devicepath(devicepath):
    if devicepath is None: return None
    devicepath = devicepath.lower ()
    for device, drive in DEVICE_DRIVES.items ():
        if devicepath.startswith (device):
            return drive + devicepath[len (device):]
        else:
            return devicepath


def get_open_files():
    se_debug = win32security.LookupPrivilegeValue (u"", win32security.SE_DEBUG_NAME)
    hToken = win32security.OpenProcessToken (
        CURRENT_PROCESS,
        ntsecuritycon.MAXIMUM_ALLOWED
    )

    try:
        return get_main_open_files()
    except x_file_handles, (context, errno):
        print "Error in", context, "with errno", errno