# Icon Overlay

## GNU/Linux

### Nautilus

Install required Nautilus addons:

    apt install python-nautilus nautilus-emblems

Create custom emblems:

    mkdir -p ~/.icons/hicolor/48x48/emblems
    cp nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

Install the extension:

    cp nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions

## macOS

TODO

## Windows

The icons overlay is implemented as a Windows callback service as described in the [official documentation](https://msdn.microsoft.com/en-us/library/windows/desktop/cc144122(v=vs.85).aspx).

The revelant source code can be found in the `tools/windows/setup-admin.iss` file and the `nxdrive/osi/windows` folder.

### Building

The setup to build the DLLs on Windows 7 is the following:
- Visual Studio Express 2010
- The [Windows SDK for Windows 7 and .NET Framework 4](https://www.microsoft.com/en-us/download/details.aspx?id=8279)
- The [Windows Driver Kit 7.1.0](https://www.microsoft.com/en-us/download/details.aspx?id=11800)
- The [Visual C++ 2010 SP1 Compiler Update](https://www.microsoft.com/en-us/download/details.aspx?id=4422)
- [Ant](https://ant.apache.org/bindownload.cgi)

On Windows 10, you should be able to install all the recent C++ dependencies with Visual Studio 2017, however you need to upgrade the project:
Once [liferay-nativity](https://github.com/liferay/liferay-nativity) is checked out, re-target the projects in `LiferayNativityShellExtensions` to the Windows 10 SDK and change the Properties > Configuration Properties > General > Platform toolset to the latest VS 2017 one.


Then modify the content of `.\windows\LiferayNativityShellExtensions\LiferayNativityUtil\UtilConstants.h` and set the `REGISTRY_ROOT_KEY` to `SOFTWARE\\Nuxeo\\Drive\\Overlays`, as well as the `PORT` to `10650`.

Then we add a `build.<username>.properties` file in it which contains the following:
```
nativity.dir=<liferay-nativity path>
nativity.version=1.0.1
ms.sdk.7.1.dir=C:/Program Files/Microsoft SDKs/Windows/v7.1
framework.dir=C:/Windows/Microsoft.NET/Framework64/v4.0.30319
```

We can then run:
```shell
ant -propertyfile build.<username>.properties build-windows-util
```
This builds a utility DLL.

Then we run:
```shell
ant -propertyfile build.<username>.properties build-windows-overlays \
    -Doverlay.name=<name> \
    -Doverlay.guid=<guid> \
    -Doverlay.id=<id> \
    -Doverlay.path=<icon>
```
The name must identify what status the icon represents, e.g. "DriveSyncedOverlay".
The guid must be a unique CLSID.
The id must be different for each icon.
The icon must be a path that points to an .ico file.

The DLLs are created in the `dist` folder.

We move them to the `nuxeo-drive/tools/windows/dll/(x86|x64)` directories.
During installation, Inno Setup will take care of running `regsvr32` on them so that they are registered with the system and executed by the Explorer.

Drive itself is responsible for:
- Writing the watched folder(s) in a `FilterFolders` value of the `HKCU\\Software\\Nuxeo\\Drive\\Overlays` register key. It should be formatted like a JSON array of strings.
- Writing `1` in an `EnableOverlay` value of the same key.
- Listening on port 50675 with a TCP socket.

The DLL will asks for status by sending a command in JSON, e.g.
```
{
    "command": "getFileIconId",
    "value": "C:\\Users\\Windows7\\Documents\\Nuxeo Drive"
}
```
and waits for a response with the status id of the target file, e.g.
```
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
