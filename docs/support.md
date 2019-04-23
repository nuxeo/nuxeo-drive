# Support

This page is targeting the current Nuxeo Drive release. You can check for older releases by adapting the current URL (replace `$VERSION` with the desired version, e.g.: 4.1.2):

```
https://github.com/nuxeo/nuxeo-drive/blob/release-$VERSION/docs/support.md
```

## Server

Nuxeo Drive always supports all versions [currently supported](https://www.nuxeo.com/legal/supported-versions/) by Nuxeo (at the time of each release).
The **only requirement** is to always have the Nuxeo Drive addon up-to-date.

Current support:

- Nuxeo Platform 7.10
- Nuxeo Platform 8.10
- Nuxeo Platform 9.10
- Nuxeo Platform 10.10
- Nuxeo Platform SNAPSHOT

History:

- `2018-01-29` (v3.0.4): dropped support for Nuxeo Platform 6.10

## Client

Officially supported platform vendors and versions:

- macOS >= 10.11, 64 bits
- Windows 7, both 32 and 64 bits
- Windows 8, both 32 and 64 bits
- Windows 8.1, both 32 and 64 bits
- Windows 10, both 32 and 64 bits

History:

- `2018-06-11` (v3.1.1): dropped support for macOS 10.10
- `2018-02-23` (v3.0.5): dropped support for macOS 10.4 - 10.9
- `2017-04-11` (v2.4.0): dropped support for Windows Vista
- `2014-04-08` (v1.3.0806): dropped support for Windows XP

### GNU/Linux

GNU/Linux support is a bit more complicated, but our developers are using Debian 8+ and Ubuntu 16.04+ on a daily basis.

You can find out how we are doing it by reading [deployment.md](https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md) and the related Shell script.

_Note_: this is a temporary situation, official support with packages is on the way.

### Known Browsers Limitations

With the Safari browser, the DirectEdit feature can be unstable (see [NXDRIVE-972](https://jira.nuxeo.com/browse/NXDRIVE-972)).
We recommend using recent versions of Firefox or Chrome for the best experience.

### Python

Nuxeo Drive is not a module but a whole package containing its own Python version and all dependencies.
If you want to use the module version as a basic module for your own software, please keep in mind that we do not offer support for dropped Python versions.

It may evolve quickly without notification as we are following the Python development cycle.

As of now, we are using the __Python 3.6.8__.

History:

- `2018-10-30` (v4.0.0): dropped support for Python 2.7
- `2014-??-??`: dropped support for Python 2.6


### Translations

Nuxeo Drive is translated in several languages. For now, officially supported ones are:

- Dutch
- English
- French
- German
- Hebrew
- Indonesian
- Italian
- Japanese
- Spanish
- Swedish
