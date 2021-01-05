# Icon Overlay

## GNU/Linux

Verify that the command is installed:
```shell
command -v gio
```

Create custom emblems:

1. Create a 24px * 24px icon.
2. The icon must be named `emblem-NAME.svg` (PNG also works).
3. Copy the icon to the appropriate folder:
```shell
cp /path/to/emblem-NAME.svg $HOME/.local/share/icons
```

Attribute emblem to folder/file:
```shell
gio set -t stringv FILE metadata::emblems emblem-NAME
```

Verification:
```shell
gio info FILE
```
`metadata::emblems` attribute should be equal to: `[emblem-NAME]`

## macOS

TODO

## Windows

The icons overlay is implemented as a Windows callback service as described in the [official documentation](https://msdn.microsoft.com/en-us/library/windows/desktop/cc144122(v=vs.85).aspx).

The revelant source code can be found in the `tools/windows/setup-admin.iss` file and the `nxdrive/osi/windows` folder.

### Building

On Windows 10, you should be able to install all the recent C++ dependencies with Visual Studio 2017.

The projects are in `tools/windows/NuxeoDriveShellExtensions`.
The `NuxeoDriveUtil` can be built by itself. The `NuxeoDriveOverlays` needs to be built once per icon.

There is a function in the deployment script that takes care of all this, just run:
    powershell .\tools\windows\deploy_ci_agent.ps1 --build_dlls

Once DLLs are compiled, we move them to the `nuxeo-drive/tools/windows/dll/(x86|x64)` directories.
During installation, Inno Setup will take care of running `regsvr32` on them so that they are registered with the system and executed by the Explorer.

Drive itself is responsible for:

- Writing the watched folder(s) in a `FilterFolders` value of the `HKCU\\Software\\Nuxeo\\Drive\\Overlays` register key. It should be formatted like a JSON array of strings.
- Writing `1` in an `EnableOverlay` value of the same key.
- Listening on port 10650 with a TCP socket.

The DLL will asks for status by sending a command in JSON, e.g.

```json
{
    "command": "getFileIconId",
    "value": "C:\\Users\\Windows7\\Documents\\Nuxeo Drive"
}
```

and waits for a response with the status id of the target file, e.g.

```json
{
    "value": "1"
}
```

### Limitation

There is a known limitation on Windows that [restricts the number of icon overlays to **15**](https://superuser.com/a/1166585/180383) (see also [Image Overlays on MSDN](https://msdn.microsoft.com/en-us/library/windows/desktop/bb761389%28v=vs.85%29.aspx#Image_Overlays)).
That limitation cannot be bypassed and Microsoft never communicated on the subject about a possible future removal or increase.

In case multiple applications using the overlays are installed (e.g. NextCloud, Dropbox, Google Drive, OneDrive  -- installed by default on Windows 10, etc.) only the 15 first registry entries in alphabetical order in `HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers` will be taken into account.

And so, it is an open war for whom will be the 1st listed by adding spaces in the beginning of the key name. For instance, [as of 2017-01-17](https://stackoverflow.com/q/41697737/1117028), Dropbox is adding 3 spaces before its name to be 1st.
Nuxeo will not take part of that endless war, we are simply adding key names like `Drive<Status>Overlay`.

To be crystal clear: the more synchronization software you have, the less chance you have to see Nuxeo Drive icons.

If you are in the situation described above, your only option is to remove or rename other registry keys like described here: [Making Icon Overlays Appear In Windows 7 and Windows 10](https://www.interfacett.com/blogs/making-icon-overlays-appear-in-windows-7-and-windows-10/).
