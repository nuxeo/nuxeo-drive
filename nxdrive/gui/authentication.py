# coding: utf-8
__all__ = ("auth",)


def auth(cls: "Application", url: str) -> None:
    """
    Authenticate through the browser.

    This authentication requires the server's Nuxeo Drive addon to include
    NXP-25519. Instead of opening the server's login page in a WebKit view
    through the app, it opens in the browser and retrieves the login token
    by opening an nxdrive:// URL.
    """
    cls.manager.open_local_file(url)
