# Windows CLI for Nuxeo Drive

That page is aimed for sysadmin, but it can be helpful for every one in time.

- Stop/Kill Nuxeo Drive
```
taskkill /im ndrive.exe /f 2>null
```
- Silently uninstall Nuxeo Drive:
```
"%USERPROFILE%\AppData\Roaming\Nuxeo Drive\unins000.exe"
```
