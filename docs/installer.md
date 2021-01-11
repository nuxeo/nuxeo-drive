# Installer

## Old Implementation

Until Drive 3.1.0, we were using [cx_Freeze](https://pypi.org/project/cx_Freeze/) in conjunction with [Esky](https://pypi.org/project/esky/) (Windows) or [py2app](https://pypi.org/project/py2app/) (macOS) to freeze the code and create installer.
It has worked for years but was preventing our move to Python 3 and Qt 5:

- The cx_Freeze update from 4.3.3 to latest 5.1.1 is impossible due to Esky incompatibility;
- The Windows installer is not ideal with lot of issues (executable information, panel configuration information, ...);
- It is not possible to sign installers and packages;
- cx_Freeze and Esky are not Python 3 compliant.

So, with the issue [NXDRIVE-730](https://jira.nuxeo.com/browse/NXDRIVE-730), we decided to seek an alternative.

## Current Implementation

### Freezer

We decided to use [PyInstaller](http://www.pyinstaller.org/) to freeze the code:

- Installation made easy;
- A unique way to build releases on GNU/Linux, macOS and Windows;
- Code-signing executables.

### Installers

Installers are available for macOS and Windows.
There is no built-in support for installer on GNU/Linux, just a universal binary (AppImage file).

#### macOS

We generate a signed DMG of the final folder created by PyInstaller and containing all required files for Drive to work.
If you want to exactly know how it is done, check the file `tools/osx/deploy_ci_agent.sh`.

#### Windows

[Inno Setup](http://www.jrsoftware.org/) is used to build the installer:

- No more modifications into the registry with Python;
- Easily expandable (customers can customize their installers);
- Installation and update more than easy (download and click on Next, Next and OK);
- No more admin rights required ([NXDRIVE-601](https://jira.nuxeo.com/browse/NXDRIVE-601));
- Installer with our logo and colors;
- Complete uninstaller (Drive files and regedit purge, but not personal files);
- Good information and logo in the panel configuration ([NXDRIVE-512](https://jira.nuxeo.com/browse/NXDRIVE-512) and [NXDRIVE-448](https://jira.nuxeo.com/browse/NXDRIVE-448));
- Possibility to sign the package;
- Installation via CLI possible;
- Installer can be built via a batch script;
- we can remove Esky and purge the monstrous `setup.py` file.

##### Installer Customization

The installer generator is drived by the file `tools\windows\setup.iss`. It is quite easy to read and understand, even easier to customize.
So if you plan to create your own Nuxeo Drive installer, this is where to look at. We put a lot of comments in the file and modifying it will not require extended technical skills.

When you are done with it, you call the *Inno Setup Compiler* with:

[//]: # (XXX_INNO_SETUP)

```batch
"C:\Program Files (x86)\Inno Setup 6\iscc.exe" /DMyAppVersion="x.y.z" "tools\windows\setup.iss"
```

That is all, ~40 seconds later, you will find a file `dist\nuxeo-drive-x.y.z.exe`: ready to deploy and install!

##### Installer Arguments

You can customize the Nuxeo Drive installation by passing custom arguments.

###### Retro-compatibility

As of Nuxeo Drive 3.1.0, we changed the way Drive is packaged. We are now creating EXE files instead of MSI.

If you used to customize the installation process, know that the same arguments are taken into account, but the way you declare them changes:

- Old: `msiexec /i nuxeo-drive.msi /qn /quiet ARG=value ...`
- New: `nuxeo-drive.exe /silent /ARG=value ...`

**Warning**: it is now highly deprecated to use the `TARGETDIR` argument. For convenient reasons, we decided to not allow the user to choose the installation folder.
So it *may* work, but we **do not support** this as it can break the auto-update and introduce other issues.

###### Mandatory arguments

Note: You cannot use one of these arguments without the other, they are complementary.

- `TARGETURL`:  The URL of the Nuxeo server.
- `TARGETUSERNAME`: The username of the user who will be using Nuxeo Drive.

###### Optional arguments

- `TARGETPASSWORD`: The password of the user who will be using Nuxeo Drive.

If you don't specify it then it will be asked to the user when Nuxeo Drive is started.

- `TARGETDRIVEFOLDER`: The path to the user synchronisation folder that will be created.

Path must include the Nuxeo Drive folder.

- `START=auto`: Start Nuxeo Drive after the installation.

###### Examples

Install Nuxeo Drive and configure the Nuxeo server to `http://localhost:8080/nuxeo` with the username `username`:

```batch
nuxeo-drive.exe /SILENT /TARGETURL="http://localhost:8080/nuxeo" /TARGETUSERNAME="username"
```

Same as above, but add the associated password:

```batch
nuxeo-drive.exe /SILENT /TARGETURL="http://localhost:8080/nuxeo" /TARGETUSERNAME="username" /TARGETPASSWORD="password"
```

A full installation, useful for large automatic deployments:

```batch
nuxeo-drive.exe /VERYSILENT /TARGETDRIVEFOLDER="%USERPROFILE%\Documents\Nuxeo Drive" /TARGETURL="http://localhost:8080/nuxeo" /TARGETUSERNAME="foo"
```

Even if `username` is wrong, it will allow the customization of the Nuxeo server on all clients. The users will be asked to enter their username and password upon the first connection.

###### Windows CLI for Nuxeo Drive

Useful commands for sysadmin, but it can be helpful to everyone at times.

- Stop/Kill Nuxeo Drive:

```batch
taskkill /im ndrive.exe /f 2>null
```

- Silently uninstall Nuxeo Drive:

```batch
"%USERPROFILE%\AppData\Local\Nuxeo Drive\unins000.exe /VERYSILENT"
```
