from logging import getLogger
from time import sleep

from nxdrive.constants import APP_NAME


log = getLogger(__name__)


def copy_clipboard() -> str:
    """Get content of the clip board."""
    # Use the import there to prevent pytest --last-failed to crash
    # when running on non Windows platforms
    import win32clipboard

    win32clipboard.OpenClipboard()
    details = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    return details


def fatal_error_dlg(app, with_details: bool = True) -> bool:
    # Check if the fatal error dialog is prompted.
    # XXX: Keep synced with FATAL_ERROR_TITLE.
    dlg = app.window(title=f"{APP_NAME} - Fatal error")
    if dlg.exists():
        if with_details:
            # Copy details
            sleep(1)
            dlg.child_window(title="Copy details").wait("visible").click()
            sleep(1)
            log.warning(f"Fatal error screen detected! Details:\n{copy_clipboard()}")
        else:
            log.warning(f"Fatal error screen detected!")

        dlg.close()
        return True
    return False


def main_window(app):
    # Return the main window.
    return app.top_window()


def share_metrics_dlg(app) -> bool:
    # Check if the pop-up to share metrics is prompted and close it.
    # XXX: Keep synced with SHARE_METRICS_TITLE.
    dlg = app.window(title=f"{APP_NAME} - Share debug info with developers")
    if dlg.exists():
        dlg.close()
        return True
    return False
