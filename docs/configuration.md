# Configuration

> Starting with Nuxeo Drive 4.0, invalid parameter names and values will make the program to stop.
> This is a quality check to ensure a good experience.

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

Parameter names are quite flexible. There is no differentiation between lowercase and uppercase, nor between hyphens and underscores.
For instance, you can specify `ssl-no-verify`, `ssl_no_verify`, `ssl_no-verify` or `SSL_No_verify`, it will be the same result.

Parameter values are taken as is, except for booleans. In that case, you can specify, in lowercase or uppercase:

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
| `ca-bundle` | None | str | File or directory with certificates of trusted CAs. If set, `ssl-no-verify` has no effect. See the `requests` [documentation](http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification) for more details.
| `chunk_limit` | 20 | int | Size in Mio above which files will be uploaded in chunks (if `chunk_upload` is `True`). Has to be above 0.
| `chunk_size` | 20 | int | Size of the chunks in Mio. Has to be above 0 and lower or equal to 20.
| `chunk_upload` | True | bool | Activate the upload in chunks for files bigger than `chunk_limit`.
| `debug` | False | bool | Activate the debug window, and debug mode.
| `delay` | 30 | int | Define the delay before each remote check.
| `force-locale` | None | str | Force the reset to the language.
| `handshake-timeout` | 60 | int | Define the handshake timeout.
| `ignored_files` | ... | list | File names to ignore while syncing.
| `ignored_prefixes` | ... | list | File prefixes to ignore while syncing.
| `ignored_suffixes` | ... | list | File suffixes to ignore while syncing.
| `locale` | en | str | Set up the language if not already defined. This can also be set up by the user from the Settings window.
| `log-filename` | None | str | The name of the log file.
| `log-level-console` | WARNING | str | Define level for console log. Can be DEBUG, INFO, WARNING, ERROR. TRACE level has been deprecated since 4.1.0, and will be treated as DEBUG.
| `log-level-file` | INFO | str | Define level for file log. Can be DEBUG, INFO, WARNING, ERROR. TRACE level has been deprecated since 4.1.0, and will be treated as DEBUG.
| `max-errors` | 3 | int | Define the maximum number of retries before considering the file as in error.
| `nofscheck` | False | bool | Disable the standard check for binding, to allow installation on network filesystem.
| `proxy-server` | None | str | Define the address of the proxy server (e.g. `http://proxy.example.com:3128`). This can also be set up by the user from the Settings window.
| `ssl-no-verify` | False | bool | Define if SSL errors should be ignored. Highly unadvised to enable this option.
| `timeout` | 30 | int | Define the socket timeout.
| `update-check-delay` | 3600 | int | Define the auto-update check delay. 0 means disabled.
| `update-site-url` | [URL](https://community.nuxeo.com/static/drive-updates) | str | Configure a custom update website. See Nuxeo Drive Update Site for more details.
| `use-analytics` | False | bool | Share anonymous usage analytics to help the developers build the best experience for you.
| `use-sentry` | True | bool | Allow sharing error reports when something unusual happen.

### Obsolete Parameters

| Parameter | Default Value | Version Removed | New Option Name | New Default Value
|---|---|---|---|---
| `beta-update-site-url` | [URL](https://community.nuxeo.com/static/drive-updates) (str) | 4.0.2 | None | None
| `beta-channel` | False (bool) | 4.0.2 | `channel` | release (str)
| `consider-ssl-errors` | True (bool) | 4.0.1 | `ssl-no-verify` | False (bool)
| `debug` | False (bool) | 4.0.0 | None | None
| `max-sync-step` | 10 (int) | 4.1.3 | none | None
| `proxy-exceptions` | None (str) | 4.0.0 | None | None
| `proxy-type` | None (str) | 4.0.0 | None | None

## Command Line Arguments

When used as a command line argument you need to prefix with the long argument modifier `--`, e.g.: `--log-level-file=DEBUG`.

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
log-level-file = DEBUG
ignored_suffixes =
    .bak
    .tmp
    .XXX
```

The `env` option from the `[DEFAULT]` section defines in which section looking for options.
Here, options defined in the `[custom]` section will be taken into account.

### Interpolation

If you are using special characters in values like:

```ini
ca_bundle = %userprofile%\.certificates
```

You may end up on such error:

```python
configparser.InterpolationSyntaxError: '%' must be followed by '%' or '(', found: '%userprofile%/.certificates'
```

This is a special processing done by the configuration parser named [values interpolation](https://docs.python.org/3/library/configparser.html#interpolation-of-values).

In that case, just double the percent sign:

```ini
ca_bundle = %%userprofile%%\.certificates
```
