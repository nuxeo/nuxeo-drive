# Usage Metrics

- Created: 2021-01-08
- Last-Modified: 2021-02-23
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>,
          Romain Grasland <rgrasland@nuxeo.com>
- Reviewer: Nelson Silva <nsilva@nuxeo.com>
- Implementer: Romain Grasland <rgrasland@nuxeo.com>
- Status: draft
- Related-Ticket: [NXDRIVE-2461](https://jira.nuxeo.com/browse/NXDRIVE-2461)

## Abstract

Document containing all usage metrics.
The document is meant to evolve with the time to keep track of all metrics we are using to make the product better.

The document can be use by the support team or anyone else needing to share the information.

## Rationale

Please have a look at [TL-370](https://jira.nuxeo.com/browse/TL-370) for details about the need and discussions about which solution to adopt.

## Specifications

Metrics are simple HTTP headers sent with the appropriate existing request.
Data is either a lowercase string, an integer or a list of integers.

Most metrics are real-time. If not, it is specified and will be sent through the `/me` endpoint.

## Metrics

### General

Metrics sent to every request.

#### User-Agent

A well-crafted string following https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/User-Agent.

It contains:

- application name and version
- installation type (`system` for system-wide or `user` user-only)
- OS name, version (`X.Y` notation only to ease filtering on that value), architecture, type (`arm64|i386|x86_64|...`)

#### NX-metric-account.number

Account number, incremented for each new account (integer).

### Direct Edit

Direct Edit feature metrics, sent at the end of an edition.

Impacted operation: `Document.Unlock`.

#### NX-metric-directEdit.conflict.hit

How many conflicts during the edition (integer).

#### NX-metric-directEdit.error.count

How many errors during the edition (integer).

#### NX-metric-directEdit.recovery.hit

How many times the document was recovered (integer).

#### NX-metric-directEdit.save.count

(lors du unlock)
(How many save per “session” (i.e before the document is closed)

How many times the user saved the file (integer).

### Direct Transfer

Direct Transfer feature metrics.

Most of those metrics are sent in real-time.

Impacted operations:

- `FileManager.CreateFolder`
- `FileManager.Import`

Impacted endpoint: `/upload`.

#### NX-metric-directTransfer.duplicate.behavior

File duplicate creation option (string). Choices: `create|ignore|override`.

#### NX-metric-directTransfer.option.newFolder

Bool when the option "new folder" is used.

#### NX-metric-directTransfer.session.number

Session number (integer).

#### NX-metric-directTransfer.session.status

Final session status (string). It is sent at the end of a session. Choices: `cancelled|done`.

Impacted endpoint: `/me`.

Real-time: ❌

### Synchronization

Metrics related to the synchronization.

#### NX-metric-sync.action

Event that triggered the transfer (string). It is sent to every request made.
Choices: `remotely_created|locally_modified|...`.

Impacted operations:

- `Blob.Get`
- `Document.Fetch`
- `NuxeoDrive.*`

Impacted endpoints:

- `/nxfile`
- `/upload`

#### NX-metric-sync.error.type

Lower-case error label (string).

Impacted endpoint: `/me`.

Real-time: ❌

#### NX-metric-sync.time

Time between the event trigger and the end of the action, in nanoseconds (integer).

Impacted endpoint: `/me`.

Real-time: ❌

### Other

Impacted endpoint: `/me`.

### NX-metric-app.crashed.hit

Real-time: ❌

### NX-metric-app.crashed.type

Real-time: ❌

### NX-metric-database.migration.failure

Real-time: ❌

Impacted endpoint: `/me`.

### NX-metric-filtered.doc UID
### NX-metric-filtered.depth INT (O = sync root, else subdoc)

Depth of the path of documents compared to their synchronization root (list of integers).

Real-time: ❌

### NX-metric-filters.syncRoot.count

How many synchronization roots (interger).

Real-time: ❌
