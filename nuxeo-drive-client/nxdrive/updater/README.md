# Auto-Update Framework

## Old Implementation

Until Drive 3.1.0, we were using the [Esky](https://pypi.org/project/esky/) framework. It has worked for years but was preventing the move to Python 3 and Qt 5:
- [Unmaintained](https://github.com/cloudmatrix/esky/commit/d0a107f6d672fd49a2aafe9581bbcdb73fbf9c6b) since 2016-08-04;
- [Discontinued](https://github.com/cloudmatrix/esky/commit/6fde3201f0335064931a6c7f7847fc5ad39001b4) since 2018-02-25;
- Errors when dealing with the Windows UAC;
- Not Python 3 compliant.

So, with the issue [NXDRIVE-1143](https://jira.nuxeo.com/browse/NXDRIVE-1143), we decided to seek an alternative.

## Alternatives

The only one viable at the time was [PyUpdater](http://www.pyupdater.org/). However:
- The documentation was lacking good/complete examples;
- Its usage was not intuitive nor easy;
- It was too broad for our needs.

## Current Implementation

We wrote our own auto-update framework knowing:
- The code freeze is done with PyInstaller;
- The macOS installer uses OS-specific commands to generate a `.dmg`;
- The Windows installer uses the Inno Setup Compiler that outputs a single `.exe`.

Currently, only macOS and Windows are supported.
There is no built-in support for auto-updater on GNU/Linux.

### Server

TODO: complete when [NXDRIVE-351](https://jira.nuxeo.com/browse/NXDRIVE-351) is done.

Note: using a secured server with `HTTPS` access only is **strongly recommended**.

The server side tree is quite simple:

    drive-updates/
        archive/
            nuxeo-drive-2.0.0.dmg
            nuxeo-drive-2.0.0.exe
        beta/
            nuxeo-drive-3.1.1.dmg
            nuxeo-drive-3.1.1.exe
        release/
            nuxeo-drive-3.1.0.dmg
            nuxeo-drive-3.1.0.exe
        nuxeo-drive.dmg
        nuxeo-drive.exe
        versions.yml

#### Folders

- `archive`: old/obsolete/non-wanted releases/betas. We keep it there for history only, nobody should use them.
- `beta`: all betas that are not releases. If one beta is going to be officially released, files are just **moved** from this folder to the `release` one.
- `release`: all official releases. Very old ones should be **moved** to the folder `archives`. The TTL is not yet decided.

#### Files

- `nuxeo-drive.dmg`: symbolic link to the latest official release for macOS;
- `nuxeo-drive.exe`: symbolic link to the latest official release for Windows;
- `versions.yml`: list of available versions and their characteristics (the format used is [YAML](http://yaml.org/)).

Example of `version.yml` content:

    2.0.0:
        min: '5.6'
        max: 7.10-HF18
        type: archive
        checksum:
            also: SHA1
            dmg: ...
            exe: ...

    3.1.0:
        min: '7.10'
        type: release
        checksum:
            algo: SHA512
            dmg: ...
            exe: ...

    3.1.1:
        min: '7.10'
        type: beta
        checksum:
            algo: MD5
            dmg: ...
            exe: ...

Each entry describes a version with:
- `type`: the release type, either an `archive`, a `beta` or a `release`. **Mandatory**.
- `checksum`: list of checksums for related files. **Mandatory**.
    - `algo`: the algorithm used, it must be one of the [hashlib](https://docs.python.org/2/library/hashlib.html) module (will use SHA256 by default).
    - `dmg`: the checksum of the file `.dmg`. **Mandatory** if you provide a macOS installer.
    - `exe`: the checksum of the file `.exe`. **Mandatory** if you provide a Windows installer.
- `min`: the minimum Nuxeo version required for this release to work with. **Mandatory**.
- `max`: the maximum Nuxeo version required for this release to work with. If not defined, Drive will consider the current Nuxeo version as acceptable to work with.

`min` and `max` can take a Hot Fix (HF) version, helpful to isolate some versions.

Notes:
- When a version is very old, and if you consider the file is growing to big, you can easily remove entries that are archived;
- A version not listed can physically exist on the server but the reverse is not true: if a version is listed, files must exist on the server.

### Client

When setting the `update-site-url` or `beta-update-site-url` parameter, it must point to `https://example.org/drive-updates/`, also:
- You do not specify `/beta` or `/release` at the end of the URL, Drive will compute the final URL depending on set options;
- Of course, if you are using a specific domain name where the tree is at the root, use only `https://example.org/`;
- The trailing slash is **not** mandatory.

Process:
1. Fetch the file `versions.yml` from the defined URL in `update-site-url` (or `beta-update-site-url`);
2. Find the latest version sorted by `type` and the current Nuxeo version;
3. If the "Auto-update" option is not checked or if there is no bound engine, stop there;
4. Download the version specific to the current OS (`.dmg` for macOS, `.exe` for Windows, ... ) into a temporary folder;
5. Verify the checksum of the downloaded file.

Then, actions taken are OS-specific.

#### macOS

1. Mount the `nuxeo-drive-x.y.z.dmg` file;
2. Backup the current `.app` in `/Applications`;
3. Copy the new `.app` to `/Applications`;
5. Unmount the `.dmg`;
6. Delete the `.dmg`;
4. Restart Drive.

#### Windows

The only action to do is to install the new version by calling `nuxeo-drive-x.y.z.exe /VERYSILENT /START=auto` from the temporary folder.
The installer will automagically:

1. Stop Drive;
2. Install the new version, it will upgrade the old one without personal data loss;
3. Start Drive.

So, a big thank you to Inno Setup! Upgrade made so easy :)
