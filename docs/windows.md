# Windows CLI for Nuxeo Drive

That page is aimed for sysadmin, but it can be helpful for every one in time.

- Stop/Kill Nuxeo Drive
```
taskkill /im ndrivew.exe /f 2>null
```
- Silently uninstall Nuxeo Drive:
```
 for /f "tokens=6,7 delims=\\" %%a in ('reg query HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall /f "nuxeo-drive" /c /d /e /s') do msiexec /x %%b /quiet /qb
```