from logging import getLogger
from time import sleep

from nxdrive.constants import APP_NAME

log = getLogger(__name__)


def cb_get() -> str:
    """Get the text data from the clipboard.
    Emulate: CTRL + V

    Copied from WindowsAbstration class, else it does not work.
    """
    import win32clipboard

    win32clipboard.OpenClipboard()
    text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    return text


def fatal_error_dlg(app, with_details: bool = True) -> bool:
    # Check if the fatal error dialog is prompted.
    # XXX: Keep synced with FATAL_ERROR_TITLE.
    log.info("Inside Fatal Error Dlg")
    print(">>>> Inside Fatal Error Dlg")
    print(f">>>> app: {app!r}")
    print(f">>>> APP_NAME: {APP_NAME!r}")
    dlg = app.window(title=f"{APP_NAME} - Fatal error")
    log.info(f">>>> dlg: {dlg!r}")
    print(f">>>> dlg: {dlg!r}")
    print(f">>>> dlg.exists(): {dlg.exists()!r}")
    print(f">>>> dlg.__dir__: {dlg.__dir__()!r}")
    print(f">>>> dlg.__dict__: {dlg.__dict__!r}")
    print(f">>>> dlg.__dict__['app']: {dlg.__dict__['app']!r}")
    print(f">>>> dlg.__dict__['app'].__dir__(): {dlg.__dict__['app'].__dir__()!r}")
    print(f">>>> dlg.__dict__['app'].__dict__: {dlg.__dict__['app'].__dict__!r}")
    if dlg.exists():
        log.info(">>>> if dlg.exists")
        print(">>>> if dlg.exists")
        if with_details:
            log.info(">>>> if with_details")
            print(">>>> if with_details")
            # Copy details
            sleep(1)
            dlg.child_window(title="Copy details").wait("visible").click()
            sleep(1)
            log.warning(f"Fatal error screen detected! Details:\n{cb_get()}")
            print(f"Fatal error screen detected! Details:\n{cb_get()}")
        else:
            log.warning("Fatal error screen detected!")
            print("Fatal error screen detected!")

        log.info(">>>> closing dlg")
        print(">>>> closing dlg")
        dlg.close()
        log.info(">>>> returning true")
        print(">>>> returning true")
        return True

    log.info(">>>> returning false")
    print(">>>> returning false")
    return False


def main_window(app):
    # Return the main window.
    sleep(10)
    return app.top_window()


def share_metrics_dlg(app) -> bool:
    # Check if the pop-up to share metrics is prompted and close it.
    # XXX: Keep synced with SHARE_METRICS_TITLE.
    dlg = app.window(title=f"{APP_NAME} - Share debug info with developers")
    print(f"$$$$ share_metrics_dlg dlg: {dlg!r}")
    print(f">>>> dlg.__dir__: {dlg.__dir__()!r}")
    print(f">>>> dlg.__dict__: {dlg.__dict__!r}")
    print(f">>>> dlg.exists(): {dlg.exists()!r}")
    # if dlg.exists():
    #     dlg.close()
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
    import os

    from selenium import webdriver

    os.environ["PATH"] = os.environ["PATH"] + ":" + os.getcwd()

    browser = webdriver.Firefox()
    try:
        return browser.current_url
    finally:
        browser.quit()
