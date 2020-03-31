# Features and Behaviors Flags

- Created: 2020-03-03
- Last-Modified: 2020-04-01
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>,
          Patrick Abgrall <pabgrall@nuxeo.com>
- Reviewer: Yannis Achour <yachour@nuxeo.com>
            Romain Grasland <rgrasland@nuxeo.com>
- Status: implemented
- Related-Ticket: [NXDRIVE-2070](https://jira.nuxeo.com/browse/NXDRIVE-2070)

## Abstract

We want to give even more control on features/behaviors to enable or not inside Nuxeo Drive.

## Rationale

Some features may be considered not safe at some point in some release.
So we would like to be able to implement one feature without being enabled.
Then we could turn on the feature when we consider it safe and stable enough.

Some features/behaviors could be turned off on-demand by IT teams.
This will leverage the global configuration file (from the server) to give "full" control on features users could use and on behaviors the application could use.

### Idea

The idea is to add 2 new configuration parameters: `behaviors` and `features`.

Both will be effective when set from the [server's configuration file](https://doc.nuxeo.com/client-apps/how-to-configure-nuxeo-drive-globally/).

Features will be also effective from the [local configuration file](https://doc.nuxeo.com/client-apps/nuxeo-drive/#configuration-file).
Meaning that one can force a feature state using its local configuration.

Behaviors are not meant to be effective when set locally because they are targeting server-side behaviors the IT teams do want to really control.

## Specifications

New parameters are a list of on/off features.

### Available Behaviors

That list may be outdated at the moment one reads it, it is not an exhaustive one:

- Server deletions (forbid document deletions on the server)

### Available Features

That list may be outdated at the moment one reads it, it is not an exhaustive one:

- Auto-update (disallow completely auto-update)
- Direct Edit
- Amazon S3 direct upload
- Direct Transfer

### Server Configuration

The file format is JSON, and the syntax would be like:

```json
{
    "behavior": {
        "server-deletion": true
    },
    "feature": {
        "auto-update"     : true,
        "direct-edit"     : true,
        "direct-transfer" : true,
        "s3"              : true
    }
}
```

### Local Configuration

The file format is INI, and the syntax would be like:

```ini
[DEFAULT]
env = myFeatures

[myFeatures]
feature.auto-update     = true
feature.direct-edit     = true
feature.direct-transfer = true
feature.s3              = true
```

### Default Values

When configuration files do not expose those new parameters, default values apply.
The up-to-date documentation can be found here: [TODO NXDOC-2083](https://jira.nuxeo.com/browse/NXDOC-2083).

At the time of that DEP, defaults are:

- `auto-update`: `true`
- `direct-edit`: `true`
- `direct-transfer`: `true`
- `s3`: `true`
- `server-deletion`: `true`

## Backward Compatibility

Starting with Nuxeo Drive 4.0.2, the server configuration is not checked in strict mode (introduced within [NXDRIVE-1438](https://jira.nuxeo.com/browse/NXDRIVE-1438)), e.g.: unknown parameters __will not__ make the application to crash.

Starting with Nuxeo Drive 4.0.0 ([NXDRIVE-1300](https://jira.nuxeo.com/browse/NXDRIVE-1300)), the local configuration is checked in strict mode, e.g.: unknown parameters __will__ make the application to crash.

So it is quite safe to setup new parameters globally as Nuxeo Drive 4.0.2 is already quite old (2018-12-06) and Nuxeo recommends to always use an up-to-date version.

## Possible Issues

New parameters should be safe to use, we do not expect regression nor issue.

But there is still something to be aware of: when one has several accounts added in the application, and if 1 of the servers restricts some features/behaviors, then the configuration will be effective for all accounts.
This is not an bug: the application is not meant to be used that way and such mechanism is not part of it.

## Rejected Ideas

### Makefile-like

A very first idea was to use more verbose "flags", inspired from the Makefile world to enable or not an option.
To disable a feature, one would prefix the option with "no-".

Server configuration:
```json
{
    "feature": [
        "s3",
        "no-direct-transfer"
    ]
}
```

Local configuration:
```ini
[DEFAULT]
env = myFeatures

[myFeatures]
feature =
    s3
    no-direct-transfer
```
