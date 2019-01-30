# GNU/Linux

## Nautilus

Install required Nautilus addons:

    apt install python-nautilus nautilus-emblems

Create custom emblems:

    mkdir -p ~/.icons/hicolor/48x48/emblems
    cp nxdrive/data/icons/overlay/nautilus/* ~/.icons/hicolor/48x48/emblems

Install the extension:

    cp nxdrive/overlay/nautilus/file_info_updater.py ~/.local/share/nautilus-python/extensions

# macOS

TODO

# Windows

The setup to build the DLL is the following:
- Windows 7
- Visual Studio Express 2010
- The [Windows SDK for Windows 7 and .NET Framework 4](https://www.microsoft.com/en-us/download/details.aspx?id=8279)
- The [Windows Driver Kit 7.1.0](https://www.microsoft.com/en-us/download/details.aspx?id=11800)
- The [Visual C++ 2010 SP1 Compiler Update](https://www.microsoft.com/en-us/download/details.aspx?id=4422)
- [Ant](https://ant.apache.org/bindownload.cgi)

Once [liferay-nativity](https://github.com/liferay/liferay-nativity) is checked out, we modify the content of `.\windows\LiferayNativityShellExtensions\LiferayNativityUtil\UtilConstants.h` and set the `REGISTRY_ROOT_KEY` to `SOFTWARE\\Nuxeo\\Drive\\Overlays`, as well as the `PORT` to `50675`.

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
The name must identify what status the icon represents, e.g. "DriveOKOverlay".
The guid must be a unique CLSID.
The id must be different for each icon.
The icon must be a path that points to an .ico file.

The DLLs are created in the `dist` folder.

We move them to the `nuxeo-drive/tools/windows/dll/(x86|x64)` directories.
During installation, Inno Setup will take care of running `regsvr32` on them so that they are registered with the system and executed by the Explorer.

Drive itself is responsible for:
- Writing the watched folder(s) in a `FilterFolders` value of the `HKCU/Software/Nuxeo\\Drive\\Overlays` register key. It should be formatted like a JSON array of strings.
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
