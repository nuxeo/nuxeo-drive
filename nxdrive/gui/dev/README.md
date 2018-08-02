This folder contains stuff for Nuxeo Drive developers.

It should be light and only for good reasons please :)

The main purpose is the authentication: if fact, since PyQt5 5.11, the WebEngine module is no more shipped on Windows 32 bits. We cannot use the WebEngine on Windows and so we moved to the user's browser with NXDRIVE-1291.

But the new way of authenticating uses the custom protocol handler `nxdrive://` which is not usable when Drive is not installed on the machine. So we came up with that solution of using the old authentication way for developers (as they are either on GNU/Linux or macOS).

Finally, files in this folder are just a copy of the old authentication way using WebEngine.
