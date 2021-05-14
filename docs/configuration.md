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
- map: simple key/value map.
- str: string

### Available Parameters

#### `behavior`

Application behavior that can be turned on/off on-demand.
That parameter cannot be set via the local configuration file: only the server has rights to define it.

- Default value (map): [...](#behaviors)
- Version added: 4.4.2

* * *

#### `beta-channel`

Use the beta channel for auto-updates.

- Default value (bool): `False`
- Version added: 2.0
- Version removed: 4.0.2, use [channel](#channel) set to `beta` instead

* * *

#### `beta-update-site-url`

Configure custom beta update website.

- Default value (str): [https://community.nuxeo.com/static/drive-updates](https://community.nuxeo.com/static/drive-updates)
- Version added: 2.0
- Version removed: 4.0.2, use [update-site-url](#update-site-url) instead

* * *

#### `big-file`

File size in MiB. Files bigger than this limit are considered "big".
This implies few tweaks in the synchronization engine like bypassing most of the expensive and time-consuming digest computations.
It is a tradeoff to handle large files as best effort.

- Default value (int): `300`
- Version added: 4.1.4

* * *

#### `ca-bundle`

File or directory with certificates of trusted Certificate Authorities.
If set, [ssl-no-verify](#ssl-no-verify) has no effect.
See the `requests` [documentation](http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification) for more details.

- Default value (str): None
- Version added: 4.0.2

* * *

#### `cert-file`

File that is a client certificate signed by the server Certificate Authorities.
If set, [cert-key-file](#cert-key-file) must also be set, otherwise it will be ignored.
See the `requests` [documentation](http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification) for more details.

- Default value (str): None
- Version added: 5.0.0

* * *

#### `cert-key-file`

File that is the key to the specified [cert-file](#cert-file).
The file MUST NOT be password protected to be usable.
If set, [cert-file](#cert-file) must also be set, otherwise it will be ignored.
See the `requests` [documentation](http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification) for more details.

- Default value (str): None
- Version added: 5.0.0

* * *

#### `channel`

Update channel. Can be `centralized`, `release`, `beta` or `alpha`.

- Default value (str): `centralized`
- Version added: 4.0.2
- Version changed: 4.2.0, changed from `release` to `centralized`


* * *

#### `chunk-limit`

Size in MiB above which files will be uploaded in chunks (if [chunk-upload](#chunk-upload) is `True`).
Has to be above 0.

- Default value (int): `20`
- Version added: 4.1.2

* * *

#### `chunk-size`

Size of the chunks in MiB. Has to be above 0 and lower or equal to 5120 (5 GiB).

- Default value (int): `20`
- Version added: 4.1.2
- Version changed: 4.5.0, bumped the upper limit from `20` to `5120`

* * *

#### `chunk-upload`

Activate the upload in chunks for files bigger than [chunk-limit](#chunk-limit).

- Default value (bool): `True`
- Version added: 4.1.2

* * *

#### `client-version`

Force the client version to run when using the centralized update channel (must be >= `4.2.0`).

- Default value (str): None
- Version added: 4.2.0

* * *

#### `consider-ssl-errors`

Define if SSL errors should be ignored.

- Default value (bool): `True`
- Version added: 2.0
- Version removed: 4.0.1, use [ssl-no-verify](#ssl-no-verify) set to `True` instead

* * *

#### `custom-metrics`

Asynchronously send custom metrics from time to time to the server.

- Default value (bool): `True`
- Version added: 5.1.0

* * *

#### `database-batch-size`

[Direct Transfer] When adding files into the database, the operation is done by batch instead of one at a time.
This option controls the batch size.

- Default value (int): `256`
- Version added: 4.4.4

* * *

#### `debug`

Activate the debug window, and debug mode.

- Default value (bool): `False`
- Version added: 2.0
- Version removed: 4.0.0

* * *

#### `delay`

Delay in seconds before each remote check (calling the [NuxeoDrive.GetChangeSummary](https://explorer.nuxeo.com/nuxeo/site/distribution/10.10/viewOperation/NuxeoDrive.GetChangeSummary) operation).

- Default value (int): `30`
- Version added: 2.0

* * *

#### `disabled-file-integrity-check`

Set to `True` to disable downloaded files integrity check.
It is a needed option when the [managed blob store key strategy](https://doc.nuxeo.com/nxdoc/hotfixes-installation-notes-for-nuxeo-platform-lts-2019/#s3-direct-upload-of-5-gb-files) is set up on the server, because there is no logic digest filled, the application would not be able to validate such files.

- Default value (bool): `False`
- Version added: 4.4.5

* * *

#### `disallowed-types-for-dt`

List of document types where Direct Transfer is not allowed.

- Default value (list):
```python
[
    "Domain",
    "Section",
]
```
- Version added: 4.5.0

* * *

#### `dt-hide-personal-space`

Allow to hide the "Personal Space" remote folder in the Direct Transfer window.

- Default value (bool): `False`
- Version added: 5.2.0

* * *

#### `exec-profile`

Define the execution profile for the application in metrics.
Can be `private` for development/QA cases or `public` for production versions.

- Default value (str): `public`
- Version added: 5.10

* * *

#### `feature`

Application features that can be turned on/off on-demand.

- Default value (map): [...](#features)
- Version added: 4.4.2

* * *

#### `force-locale`

Force the reset to the language.

- Default value (str): None
- Version added: 2.0

* * *

#### `handshake-timeout`

Define the handshake timeout in seconds.

- Default value (int): `60`
- Version added: 2.0

* * *

#### `ignored-files`

Lowercase file patterns to ignore while syncing.

- Default value (list):
```python
[
    r"^atmp\d+$",
]
```
- Version added: 2.4.1

* * *

#### `ignored-prefixes`

Lowercase file prefixes to ignore while syncing.

- Default value (list):
```python
[
    ".",
    "desktop.ini",
    "icon\r",
    "thumbs.db",
    "~$",
]
```
- Version added: 2.4.1

* * *

#### `ignored-suffixes`

Lowercase file suffixes to ignore while syncing.

- Default value (list):
```python
[
    ".bak",
    ".crdownload",
    ".dwl",
    ".dwl2",
    ".idlk",
    ".lnk",
    ".lock",
    ".nxpart",
    ".part",
    ".partial",
    ".swp",
    ".tmp",
    "~",
]
```
- Version added: 2.4.1
- Version changed: 4.1.0, added `.idlk` (Adobe InDesign lock files)

* * *

#### `locale`

Set up the language if not already defined.
This can also be set up by the user from the Settings window.

- Default value (str): `en`
- Version added: 2.0

* * *

#### `log-filename`

The name of the log file.
If not set, defaults to `nxdrive.log`.

- Default value (str): None
- Version added: 2.0

* * *

#### `log-level-console`

Define level for console log.
Can be `DEBUG`, `INFO`, `WARNING` or `ERROR`.

- Default value (str): `WARNING`
- Version added: 2.0
- Version changed: 4.1.0, `TRACE` level has been deprecated and is treated as `DEBUG`
- Version changed: 5.2.0, `TRACE` level is removed

* * *

#### `log-level-file`

Define level for file log.
Can be `DEBUG`, `INFO`, `WARNING` or `ERROR`.

- Default value (str): `INFO`
- Version added: 2.0
- Version changed: 4.1.0, `TRACE` level has been deprecated and is treated as `DEBUG`
- Version changed: 5.2.0, `TRACE` level is removed

* * *

#### `max-errors`

Define the maximum number of retries before considering the document as in error.

- Default value (int): `3`
- Version added: 2.0

* * *

#### `max-sync-step`

Number of consecutive sync operations to perform without refreshing the internal state DB.

- Default value (int): `10`
- Version added: 2.0
- Version removed: 4.1.3

* * *

#### `nofscheck`

Disable the standard check for binding, to allow installation on network filesystem.

- Default value (bool): `False`
- Version added: 2.0.911

* * *

#### `oauth2-authorization-endpoint`

The URL of the authorization endpoint for OAuth2.

- Default value (str): None
- Version added: 5.2.0

* * *

#### `oauth2-client-id`

Oauth2 client ID.

- Default value (str): `nuxeo-drive`
- Version added: 5.2.0

* * *

#### `oauth2-client-secret`

OAuth2 client secret.

- Default value (str): None
- Version added: 5.2.0

* * *

#### `oauth2-scope`

OAuth2 scope.
It is a mandatory parameter when using ADFS, for instance.

- Default value (str): None
- Version added: 5.2.0

* * *

#### `oauth2-openid-configuration-url`

The URL of the [OpenID Provider Configuration](https://openid.net/specs/openid-connect-discovery-1_0.html#ProviderConfig) for OAuth2.
When specified, [oauth2-authorization-endpoint](#oauth2-authorization-endpoint) and [oauth2-token-endpoint](#oauth2-token-endpoint) parameters will be set according to values found in that document, even if they are already defined.

The awaited value must be of the form `https://server.com/.well-known/openid-configuration`.

- Default value (str): None
- Version added: 5.2.0

* * *

#### `oauth2-token-endpoint`

The URL of the token endpoint for OAuth2.

- Default value (str): None
- Version added: 5.2.0

* * *


#### `proxy-exceptions`

Define URLs exception for the proxy.

- Default value (str): None
- Version added: 2.0
- Version removed: 4.0

* * *

#### `proxy-server`

Define the address of the proxy server (e.g. `http://proxy.example.com:3128`).
This can also be set up by the user from the Settings window.

- Default value (str): None
- Version added: 2.0

* * *

#### `proxy-type`

Define proxy type.
This can also be set up by the user from the Settings window.

- Default value (str): None
- Version added: 2.0
- Version removed: 4.0, pass the scheme directly in the [proxy-server](#proxy-server) URL

* * *

#### `ssl-no-verify`

Define if SSL errors should be ignored.
Highly unadvised to enable this option.

- Default value (bool): `False`
- Version added: 4.0.1

* * *

#### `sync-and-quit`

Launch the synchronization and then exit the application.

- Default value (bool): `False`
- Version added: 4.2.0

* * *

#### `synchronization-enabled`

Synchronization features are enabled.
If set to `False`, nothing will be downloaded/uploaded/synchronized but Direct Edit and Direct Transfer features will work.

- Default value (bool): `False`
- Version added: 4.4.0
- Version changed: 5.2.0, changed from `True` to `False`

The option is deprecated since 5.2.0 and will be removed in a future release. Use `feature.synchronization` instead.

* * *

#### `timeout`

Define the socket timeout in seconds.

- Default value (int): `30`
- Version added: 2.0

* * *

#### `tmp-file-limit`

File size in MiB.
Files smaller than this limit will be written at once to the file rather than chunk by chunk.

- Default value (float): `10.0`
- Version added: 4.1.4

* * *

#### `update-check-delay`

Define the auto-update check delay in seconds.
0 means disabled.

- Default value (int): `3600`
- Version added: 2.0

* * *

#### `update-site-url`

Configure a custom update website.
See Nuxeo Drive Update Site for more details.

- Default value (str): [https://community.nuxeo.com/static/drive-updates](https://community.nuxeo.com/static/drive-updates)
- Version added: 2.0

* * *

#### `use-analytics`

Share anonymous usage analytics to help the developers build the best experience for you.

- Default value (bool): `False`
- Version added: 4.1.0
- Version changed: 4.4.5, a minimal set of GDPR-information is sent even if set to `False` (see [NXDRIVE-2254](https://jira.nuxeo.com/browse/NXDRIVE-2254))

#### `use-idempotent-requests`

Control whenever specific HTTP calls should be made idempotent or not.

- Default value (bool): `False`
- Version added: 5.1.1

It requires [NXP-29978](https://jira.nuxeo.com/browse/NXP-29978) on the server.

If enabled, those requests will be impacted:
- `FileManager.Import` (Direct Transfer)
- `NuxeoDrive.CreateFile` (synchronization)

* * *

#### `use-sentry`

Allow sharing error reports when something unusual happens.
This parameter is critical for the product's health, please do not not turn it off.

- Default value (bool): `True`
- Version added: 4.1.0

## Behaviors

The application can be tweaked using on-demand on/off options via the `behavior` parameter.
As this is targeting server actions, this parameter cannot be set via the local configuration file but only via the server configuration one.

Available behaviors:

| Parameter | Default Value (bool) | Version Added | Description
|---|---|---|---
| `server_deletion` | true | 4.4.2 | Allow or disallow server deletions.

Here is how to tweak behaviors via the server configuration file:

```json
{
  "behavior": {
    "server-deletion": true
  }
}
```

## Features

Several features can be turned on/off on-demand via the `feature` parameter.
This parameter can be set via the local configuration file and the server configuration one.

If the same feature is defined locally and remotely, then only the local value will be taken into account.

Available features:

| Parameter | Default Value (bool) | Version Added | Description
|---|---|---|---
| `auto_updates` | true | 4.4.2 | Allow or disallow auto-updates.
| `direct_edit` | true | 4.4.2 | Allow or disallow Direct Edit.
| `direct_transfer` | true | 4.4.2 | Allow or disallow Direct Transfer.
| `synchronization` | false | 5.2.0 | Enable or disable the synchronization features.
| `s3` | true | 4.4.2 | Allow or disallow using Amazon S3 direct uploads.

Here is how to tweak features via the local configuration file:

```ini
feature.auto-update     = true
feature.direct-edit     = true
feature.direct-transfer = true
feature.synchronization = true
feature.s3              = true
```

Here is how to tweak features via the server configuration file:

```json
{
  "feature": {
    "auto-update"     : true,
    "direct-edit"     : true,
    "direct-transfer" : true,
    "synchronization" : true,
    "s3"              : true
  }
}
```

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
