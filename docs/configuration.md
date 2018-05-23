# Configuration

Nuxeo Drive has different parameters that you can set up through:
- the REST API endpoint `/drive/configuration` served by the server (since [NXP-22946](https://jira.nuxeo.com/browse/NXP-22946) and Drive 3.0.0),
- a `$HOME/.nuxeo-drive/config.ini` file,
- a registry key inside `HKEY_CURRENT_USER\Software\Nuxeo\Drive` (since Drive 3.1.0, Windows only),
- the command line.
Each of these ways overrides the previous one.

## Parameters

| Parameter | Default Value | Description
|---|---|---
| `beta-update-site-url` | https://community.nuxeo.com/static/drive-updates | Configure custom beta update website.
| `consider-ssl-errors` | False | Define if SSL errors should be ignored.
| `debug` | False | Activate the debug window, and debug mode.
| `delay` | 30 | Define the delay before each remote check.
| `force-locale` | None | Force the reset to the language.
| `handshake-timeout` | 60 | Define the handshake timeout.
| `locale` | en | Set up the language if not already defined. This can also be set up by the user from the Settings window.
| `log-filename` | None | The name of the log file.
| `log-level-console` | INFO | Define level for console log. Can be TRACE, DEBUG, INFO, WARNING, ERROR.
| `log-level-file` | DEBUG | Define level for file log. Can be TRACE, DEBUG, INFO, WARNING, ERROR. This can also be set up from the Settings window.
| `max-errors` | 3 | Define the maximum number of retries before considering the file as in error.
| `ndrive-home` | `$HOME/.nuxeo-drive` | Define the personal folder.
| `nofscheck` | False | Disable the standard check for binding, to allow installation on network filesystem.
| `proxy-exceptions` | None | Define URLs exception for the proxy.
| `proxy-server` | None | Define proxy server. This can also be set up by the user from the Settings window.
| `proxy-type` | None | Define proxy type. This can also be set up by the user from the Settings window.
| `timeout` | 30 | Define the socket timeout.
| `update-check-delay` | 3600 | Define the auto-update check delay. 0 means disabled.
| `update-site-url` | https://community.nuxeo.com/static/drive-updates | Configure a custom update website. See Nuxeo Drive Update Site for more details.

## Command Line Arguments

When used as a command line argument you need to prefix with the long argument modifier `--`, e.g.: `--log-level-file TRACE`.

## Configuration File

Instead of using command line arguments, you can create the `config.ini` file into the `$HOME/.nuxeo-drive` folder.
The file syntax is:

    [DEFAULT]
    env = custom

    [custom]
    log-level-file = TRACE
    debug = False

You can add parameters inside the `[custom]` section.
