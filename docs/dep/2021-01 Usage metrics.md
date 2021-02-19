# Usage Metrics

- Created: 2021-01-08
- Last-Modified: 2021-02-19
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>
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

### Context

Metrics sent to every request.

#### User-Agent

A string containing the application name and version, and OS details. It follows

https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/User-Agent

It must contain:
- application name and version
- installation type (`system` for system-wide or `user` user-only)
- OS name, version (`X.Y` notation only to ease filtering on that value), architecture, type (`arm64|i386|x86_64|...`)


#### X-Account-Number

Account number, incremented for each new account (integer). It is sent to every request.

```python
"X-Account-Number": 1
```

#### X-Application-Name

Application name (string). It is sent to every request.

```python
"X-Application-Name": "Nuxeo Drive"
```

#### X-Device-Id

Uniq ID for the account on the machine (string). It is sent to every request.

```python
"X-Device-Id": "hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh"
```

#### X-User-Id

Username (string). It is sent to every request.

```python
"X-User-Id": "alice"
```

### X-Direct-Edit

Direct Edit feature metrics, sent at the end of an edition.

Impacted operation: `Document.Unlock`.

#### X-Direct-Edit-Conflict-Count

How many conflicts during the edition (integer).

```python
"X-Direct-Edit-Conflict-Count": 0
```

#### X-Direct-Edit-Error-Count

How many errors during the edition (integer).

```python
"X-Direct-Edit-Error-Count": 0
```

#### X-Direct-Edit-Extension

File extension (string).

```python
"X-Direct-Edit-Extension": "docx|..."
```

#### X-Direct-Edit-Recovery-Count

How many times the document was recovered (integer).

```python
"X-Direct-Edit-Recovery-Count": 0
```

#### X-Direct-Edit-Save-Count

How many times the user saved the file (integer).

```python
"X-Direct-Edit-Save-Count": 2
```

### X-Direct-Transfer

Direct Transfer feature metrics.

Most of those metrics are sent in real-time.

Impacted operations:

- `FileManager.CreateFolder`
- `FileManager.Import`
- `FileManager.ImportWithProperties` (not yet, but soon)

Impacted endpoint: `/upload`.

#### X-Direct-Transfer-Duplicate-Behavior

File duplicate creation option (string).

```python
"X-Direct-Transfer-Duplicate-Behavior": "create|ignore|override"
```

#### X-Direct-Transfer-Session-Number

Session number (integer).

```python
"X-Direct-Transfer-Session-Number": 1
```

#### X-Direct-Transfer-Session-Status

Final session status (string). It is sent at the end of a session.

Impacted endpoint: `/me`.

Real-time: ❌

```python
"X-Direct-Transfer-Session-Status": "cancelled|done"
```

### X-Sync

Metrics related to the synchronization.

#### X-Sync-Action

Event that triggered the transfer (string). It is sent to every request made.

Impacted operations:

- `Blob.Get`
- `Document.Fetch`
- `NuxeoDrive.*`

Impacted endpoints:

- `/nxfile`
- `/upload`

```python
"X-Sync-Action": "remotely_created|locally_modified|..."
```

#### X-Sync-Error

Error label (string).

Impacted endpoint: `/me`.

Real-time: ❌

```python
"X-Sync-Error": "dedup|...",
```

#### X-Sync-Time

Time between the event trigger and the end of the action, in nanoseconds (integer).

Impacted endpoint: `/me`.

Real-time: ❌

```python
"X-Sync-Time": 4200000000
```

### X-Filter

Metrics related to filters.

Impacted endpoint: `/me`.

### X-Filter-Count

Ho many filtered documents (integer).

Real-time: ❌

```python
"X-Filter-Count": 1
```

### X-Filter-Depths

Depth of the path of documents compared to their synchronization root (list of integers).

Real-time: ❌

```python
"X-Filter-Depths": [1, 5, 5, 15]
```

### X-Filter-Root-Count

How many synchronization roots (interger).

Real-time: ❌

```python
"X-Filter-Root-Count": 1
```
