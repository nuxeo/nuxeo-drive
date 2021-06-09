# Support

This page is targeting the current Nuxeo Drive release. You can check for older releases by adapting the current URL (replace `$VERSION` with the desired version, e.g.: 4.1.2):

```
https://github.com/nuxeo/nuxeo-drive/blob/release-$VERSION/docs/support.md
```

## Server

Nuxeo Drive always supports all versions [currently supported](https://www.nuxeo.com/legal/supported-versions/) by Nuxeo (at the time of each release), with those [minimum HF requirements](https://doc.nuxeo.com/client-apps/nuxeo-drive-faq/#what-are-the-required-nuxeo-versionshotfixes-when-using-a-drive-client-version).
The **only requirement** is to always have the Nuxeo Drive addon up-to-date.

History:

- `2018-01-29` (v3.0.4): dropped support for Nuxeo Platform 6.0

## Client

Check the [supported OS](https://doc.nuxeo.com/client-apps/nuxeo-drive-faq/#what-are-the-supported-os) page.

History:

- `2021-02-19` (v5.0.0): dropped support for macOS 10.12
- `2021-02-19` (v5.0.0): dropped support for Windows 7
- `2020-12-15` (v4.5.0): dropped support for Windows 7 without SP1
- `2019-11-14` (v4.3.0): dropped support for macOS 10.11
- `2019-09-26` (v4.2.0): added support for GNU/Linux
- `2018-06-11` (v3.1.1): dropped support for macOS 10.10
- `2018-02-23` (v3.0.5): dropped support for macOS 10.4 - 10.9
- `2017-04-11` (v2.4.0): dropped support for Windows Vista
- `2014-04-08` (v1.3.0806): dropped support for Windows XP

### Known Browsers Limitations

With the Safari browser, the Direct Edit feature can be unstable (see [NXDRIVE-972](https://jira.nuxeo.com/browse/NXDRIVE-972)).
We recommend using recent versions of Firefox or Chrome for the best experience.

### Python

Nuxeo Drive is not a module, but a whole package containing its own Python version and all dependencies.
If you want to use the module version as a basic module for your own software, please keep in mind that we do not offer support for dropped Python versions.

It may evolve quickly without notification as we are following the Python development cycle.

[//]: # (XXX_PYTHON)

As of now, we are using the __Python 3.9.5__.

History:

- `2021-02-19` (v5.0.0): dropped support for Python 3.8
- `2020-12-15` (v4.5.0): dropped support for Python 3.7
- `2019-06-17` (v4.1.4): dropped support for Python 3.6
- `2018-10-30` (v4.0.0): dropped support for Python 2.7
- `2014-??-??`: dropped support for Python 2.6

### Translations

Nuxeo Drive is translated in several languages. For now, officially supported ones are:

- Basque
- Dutch
- English
- French
- German
- Indonesian
- Italian
- Japanese
- Polish
- Spanish
- Swedish
