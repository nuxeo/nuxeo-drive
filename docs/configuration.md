# Configuration

Nuxeo Drive has different parameters that you can set up through:

- The REST API endpoint `/drive/configuration` served by the server (since [NXP-22946](https://jira.nuxeo.com/browse/NXP-22946) and Drive 3.0.0).
- The command line.
- A registry key inside `HKEY_CURRENT_USER\Software\Nuxeo\Drive` (since Drive 3.1.0, Windows only).
- A `config.ini` file that can be located in different places:
  - next to the Nuxeo Drive executable
  - from the `$HOME/.nuxeo-drive` folder
  - from the current working directory

Each of these ways overrides the previous one.

## Parameters

### Names and Values

Parameters' names are quite flexible. For instance you can specify `ssl-no-verify`, `ssl_no_verify` or `ssl_no-verify`: same result.

Parameters' values are even more flexible. If the value is a boolean, you can specify (case insensitive):

- `true`, `1`, `on`, `yes` or `oui` to enable
- `false`, `0`, `off`, `no` or `non` to disable

### Value Types

- bool: boolean
- int: integer
- list: list of strings (one item by line)
- str: string

### Available Parameters

| Parameter | Default Value | Type | Description
|---|---|---|---
| `beta-update-site-url` | [URL](https://community.nuxeo.com/static/drive-updates) | str | Configure custom beta update website.
| `ca-bundle` | None | str | File or directory with certificates of trusted CAs. If set, `ssl-no-verify` has no effect. See the `requests` [documentation](http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification) for more details.
| `debug` | False | bool | Activate the debug window, and debug mode.
| `delay` | 30 | int | Define the delay before each remote check.
| `force-locale` | None | str | Force the reset to the language.
| `handshake-timeout` | 60 | int | Define the handshake timeout.
| `ignored_files` | ... | list | File names to ignore while syncing.
| `ignored_prefixes` | ... | list | File prefixes to ignore while syncing.
| `ignored_suffixes` | ... | list | File suffixes to ignore while syncing.
| `locale` | en | str | Set up the language if not already defined. This can also be set up by the user from the Settings window.
| `log-filename` | None | str | The name of the log file.
| `log-level-console` | INFO | str | Define level for console log. Can be TRACE, DEBUG, INFO, WARNING, ERROR.
| `log-level-file` | DEBUG | str | Define level for file log. Can be TRACE, DEBUG, INFO, WARNING, ERROR.
| `max-errors` | 3 | int | Define the maximum number of retries before considering the file as in error.
| `nofscheck` | False | bool | Disable the standard check for binding, to allow installation on network filesystem.
| `proxy-server` | None | str | Define the address of the proxy server (e.g. `http://proxy.example.com:3128`). This can also be set up by the user from the Settings window.
| `ssl-no-verify` | False | bool | Define if SSL errors should be ignored. Highly unadvised to enable this option.
| `timeout` | 30 | int | Define the socket timeout.
| `update-check-delay` | 3600 | int | Define the auto-update check delay. 0 means disabled.
| `update-site-url` | [URL](https://community.nuxeo.com/static/drive-updates) | str | Configure a custom update website. See Nuxeo Drive Update Site for more details.

### Obsolete Parameters

| Parameter | Default Value | Version Removed | New Option Name | New Default Value
|---|---|---|---|---
| `consider-ssl-errors` | True (bool) | 4.0.1 | `ssl-no-verify` | False (bool)

## Command Line Arguments

When used as a command line argument you need to prefix with the long argument modifier `--`, e.g.: `--log-level-file=TRACE`.

## Configuration File

The format of the `config.ini` file is as following:

```ini
[DEFAULT]
env = custom

[no-updates]
; Unused section
update-check-delay = 0

[custom]
ca_bundle = C:\certificates\terena-ssl.crt
debug = False
log-level-file = TRACE
ignored_suffixes =
    .bak
    .tmp
    .XXX
```

The `env` option from the `[DEFAULT]` section defines in which section looking for options.
Here, options defined in the `[custom]` section will be taken into account.
