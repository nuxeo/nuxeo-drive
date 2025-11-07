"""
IMPORTANT: WINDOWS ONLY MODULE

This module will launch a thread to detect if ndrive.exe is the Clipboard Owner for a specific time.
If yes, it will restart Nuxeo Drive to avoid clipboard issues on Windows.
"""

import threading
import time
from logging import getLogger

from .constants import WINDOWS

__all__ = ["ClipboardMonitorThread"]

log = getLogger(__name__)


class ClipboardMonitorThread(threading.Thread):
    """Thread to monitor clipboard ownership."""

    def __init__(
        self, check_interval: float = 1.0, ownership_threshold: float = 10.0
    ) -> None:
        super().__init__(daemon=True)
        log.info("Created ClipboardMonitorThread")
        self.check_interval = check_interval
        self.ownership_threshold = ownership_threshold

    def run(self) -> None:
        """Run the clipboard monitoring."""
        if not WINDOWS:
            return

        import ctypes
        import os
        import subprocess
        import sys

        import win32clipboard  # type: ignore
        import win32process  # type: ignore

        ndrive_exe = "ndrive.exe"  # Use a dummy name for testing
        ownership_start_time = None

        while True:
            time.sleep(self.check_interval)
            try:
                hwnd = win32clipboard.GetClipboardOwner()
                if hwnd:
                    # Get the process ID from the window handle
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    # Get the process handle
                    process_handle = ctypes.windll.kernel32.OpenProcess(
                        0x0400 | 0x0010, False, pid
                    )
                    if process_handle:
                        # Get the executable name
                        exe_name = ctypes.create_unicode_buffer(260)
                        size = ctypes.c_ulong(260)
                        ctypes.windll.kernel32.QueryFullProcessImageNameW(
                            process_handle, 0, exe_name, ctypes.byref(size)
                        )
                        ctypes.windll.kernel32.CloseHandle(process_handle)

                        exe_basename = os.path.basename(exe_name.value)

                        if exe_basename in ndrive_exe:
                            if ownership_start_time is None:
                                ownership_start_time = time.time()
                                log.warning(
                                    f"ndrive.exe detected as clipboard owner, "
                                    f"monitoring for {self.ownership_threshold}s..."
                                )
                            elif (
                                time.time() - ownership_start_time
                                >= self.ownership_threshold
                            ):
                                log.warning(
                                    f"Clipboard owned by ndrive.exe for "
                                    f"{self.ownership_threshold}s, restarting Nuxeo Drive..."
                                )
                                subprocess.Popen([sys.executable])
                                os._exit(0)
                        else:
                            ownership_start_time = None
                    else:
                        # Could not open process handle
                        ownership_start_time = None
                else:
                    # No clipboard owner
                    ownership_start_time = None
            except Exception as e:
                log.debug(f"Error checking clipboard owner: {e}")
                ownership_start_time = None
