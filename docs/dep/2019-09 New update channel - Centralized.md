# Add a new update channel: Centralized

- Created: 2019-09-02
- Last-Modified: 2019-09-10
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>,
          Patrick Abgrall <pabgrall@nuxeo.com>
- Status: implemented
- Related-Ticket: [NXDRIVE-1803](https://jira.nuxeo.com/browse/NXDRIVE-1803)

## Abstract

Add a new update channel to let the administrators manage all Nuxeo Drive versions.

## Rationale

Current [documented procedure](https://doc.nuxeo.com/client-apps/nuxeo-drive-update-site/) to manage the Nuxeo Drive client upgrade strategy assumes the customer will replicate the Nuxeo Drive upgrade site and update the upgrade URL on the client-side. Or the clients must be told not to upgrade automatically.

This puts effectively Nuxeo in charge of managing the software landscape of customer productions.
In case of incompatibility or problems introduced by a later version, the default strategy is "next version".
To implement "last working version and no automatic upgrade", the administrator must put in place the process documented above or act on the client-side to disable automated upgrade of clients...

### Idea

What is requested is that the Administrator can force from a central place a given version of Nuxeo Drive on the client-side via configuration only.
This would put the software landscape in production administrators hands in a simple and direct way.

## Specifications

### Server Side

We will leverage de [global configuration capabilities](https://doc.nuxeo.com/client-apps/how-to-configure-nuxeo-drive-globally/) to define a new option named `client_version`.

It will be a string representing a Nuxeo Drive version, e.g.: `4.2.0`.

### Client Side

A new update channel will be added, `Centralized`, that will be the default choice at installation.

To resume, the update priority will be:

1. Centralized
2. Release
3. Beta
4. Alpha

When the `Centralized` channel is used, the version that will be installed is the one set by the Administrator in the `client_version` option.

Notes:

* If the current update channel is `Centralized` and no `client_version` set, the `Release` channel will be used.
* The current update channel will not be changed for users doing an update.

## Downsides

Those are questions or preocupations that are kept for historical reasons only. None of those are actual issues.

### Cyclic Updates on Nuxeo Drive 4.x

The new update option `client_version` will be implemented in the next Nuxeo Drive version (4.2.0).

So if the Administrator sets the client version to an older version, that version will be installed.

* If the desired version is less than `4.0.0`, see [Impossible to Start Nuxeo Drive 3.x](#impossible-to-start-nuxeo-drive-3.x).
* If the desired version is greater or equal to `4.0.0` and less than `4.2.0`, that old Nuxeo Drive version does not understand the new update channel.
* It will use the `Release` channel by default and thus updating to the newest Nuxeo Drive version, creating cyclic updates.

This is known but we also need to move forward.
So the good answer will be to document that behavior and add a protection in Nuxeo Drive itself by setting a minimal version allowed to be installed via this option.

### Impossible to Start Nuxeo Drive 3.x

This will not work for Nuxeo Drive 3.x. But those versions are obsolete and unsupported for a while.
Setting the new option `client_version` will just break Nuxeo Drive as options are checked, and if it is not a known one, Nuxeo Drive raises a fatal error.

To be more clear, users using Nuxeo Drive 2.x or 3.x will have issues if administrators are using the new `client_version` option.

### Broken Updates

The only implemented check will be to ensure the `client_version` is greater or equal to `4.2.0`.

There will be no other checks so that administrators can use alpha, beta and release versions.

This might lead to unusable or instable versions of the application.
This is known and now that administrators are handling that, it is their responsibility to ensure they do not deploy a problematic version of Nuxeo Drive.
