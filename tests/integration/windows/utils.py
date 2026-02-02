from logging import getLogger
from time import sleep

from nxdrive.constants import APP_NAME

log = getLogger(__name__)


def cb_get() -> str:
    """Get the text data from the clipboard.
    Emulate: CTRL + V

    Copied from WindowsAbstration class, else it does not work.
    """
    print("cb_get called")
    import win32clipboard

    win32clipboard.OpenClipboard()
    text = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
    win32clipboard.CloseClipboard()
    return text


def window_exists(dlg, with_details: bool = True) -> bool:
    """Check if app.window (dlg) exists and handle it."""
    print(f"window_exists called with dlg={dlg}, with_details={with_details}")

    if dlg.exists():
        if with_details:
            # Copy details
            sleep(1)
            dlg.child_window(title="Copy details").wait("visible").click()
            sleep(1)
            log.warning(f"Fatal error screen detected! Details:\n{cb_get()}")
        else:
            log.warning("Fatal error screen detected!")

        dlg.close()
        return True
    return False


def fatal_error_dlg(
    app, with_details: bool = True, wait_timeout_multiplier: int = 0
) -> bool:
    # Check if the fatal error dialog is prompted.
    # XXX: Keep synced with FATAL_ERROR_TITLE.
    print(
        f"fatal_error_dlg called with app={app}, \
        with_details={with_details}, \
        wait_timeout_multiplier={wait_timeout_multiplier}"
    )

    import pywinauto

    dlg = app.window(title=f"{APP_NAME} - Fatal error")
    log.info(f"Error Window exists: {dlg.exists()!r}")

    if wait_timeout_multiplier == 0:
        if window_exists(dlg, with_details):
            return True
    else:
        # Check instantly if fatal error dialog exists
        if window_exists(dlg, with_details):
            return True

        # If not, then wait for it
        # Wait for dialog to appear if wait_timeout_multiplier is enabled
        try:
            dlg.wait("exists", timeout=10 * wait_timeout_multiplier, retry_interval=1)
            # Dialog appeared after waiting - handle it now
            if window_exists(dlg, with_details):
                return True
        except pywinauto.timings.TimeoutError:
            log.error(
                f"Fatal error dialog did not appear within {wait_timeout_multiplier * 10} seconds."
            )

    return False


def main_window(app):
    # Return the main window.
    print(f"main_window called with app={app}")
    sleep(10)
    return app.top_window()


def share_metrics_dlg(app) -> bool:
    # Check if the pop-up to share metrics is prompted and close it.
    # XXX: Keep synced with SHARE_METRICS_TITLE.
    print(f"share_metrics_dlg called with app={app}")
    dlg = app.window(title=f"{APP_NAME} - Share debug info with developers")
    if dlg:
        try:
            dlg.close()
        except Exception:
            log.warning("Window can not be closed!")
        return True
    return False


def get_opened_url() -> str:
    """Return the current opened URL and quit the browser."""
    # For the drive location
    # https://pypi.org/project/selenium/, Drivers section
    # Let's say the binary is at the root of the repository:
    print("get_opened_url called")
    import os

    from selenium import webdriver

    os.environ["PATH"] = os.environ["PATH"] + ":" + os.getcwd()

    browser = webdriver.Firefox()
    try:
        return browser.current_url
    finally:
        browser.quit()
