# Sentry advanced analytics metrics

This page lists every metric emitted when **Allow advanced analytics** is
enabled (`Options.use_analytics = true`). The consent-independent
`drive.first_run` metric is intentionally excluded.

The payloads below are examples only. Values, timestamps, trace identifiers,
release numbers, and operation attributes vary at runtime.

## Common payload fields

Sentry SDK 2.44 represents each metric as a `trace_metric` item. Before it is
serialized into an envelope, the metric passed to `before_send_metric` has this
shape:

```json
{
  "timestamp": 1787125986.04776,
  "trace_id": "72d875f54b31447fac8c03fffdef5e06",
  "span_id": "a708f04c71b283ac",
  "name": "drive.engine.sync_files",
  "type": "gauge",
  "value": 42.0,
  "unit": null,
  "attributes": {
    "sentry.sdk.name": "sentry.python",
    "sentry.sdk.version": "2.44.0",
    "sentry.environment": "production",
    "sentry.release": "6.0.0"
  }
}
```

The SDK supplies the timestamp, trace and span identifiers, and `sentry.*`
attributes. Drive supplies the metric name, value, unit, and operation-specific
attributes described below. For `drive.sync.duration` and `drive.sync.size`,
Drive removes all attributes before sending.

## Complete metric inventory

| Metric name | Type | Unit | Dummy value | Drive attributes | Emission |
| --- | --- | --- | ---: | --- | --- |
| `drive.sync.duration` | Distribution | `nanosecond` | `1250000000.0` | None | After a synchronization operation completes. |
| `drive.sync.size` | Distribution | `byte` | `1048576.0` | None | With the duration after a synchronization operation completes. |
| `drive.direct_edit.duration` | Distribution | `millisecond` | `250.0` | `{"action": "open", "extension": ".pdf"}` | After a Direct Edit open or edit operation. |
| `drive.direct_transfer.size` | Distribution | `byte` | `1048576.0` | `{"type": "file"}` | After a Direct Transfer operation completes. |
| `drive.engine.conflicted_files` | Gauge | None | `2.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.error_files` | Gauge | None | `1.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.files_size` | Gauge | None | `536870912.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.invalid_credentials` | Gauge | None | `0.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.sync_files` | Gauge | None | `120.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.sync_folders` | Gauge | None | `35.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.syncing` | Gauge | None | `3.0` | None | When the analytics worker starts, then hourly, for each engine. |
| `drive.engine.unsynchronized_files` | Gauge | None | `4.0` | None | When the analytics worker starts, then hourly, for each engine. |

`drive.engine.invalid_credentials` originates as a boolean. The SDK serializes
`false` as `0.0` and `true` as `1.0`. Engine identifiers are not attached to the
gauge payloads. The non-numeric `uid` returned by `Engine.get_metrics()` is not
sent.

## Distribution payload examples

### Synchronization duration

```json
{
  "timestamp": 1787125986.04776,
  "trace_id": "72d875f54b31447fac8c03fffdef5e06",
  "span_id": "a708f04c71b283ac",
  "name": "drive.sync.duration",
  "type": "distribution",
  "value": 1250000000.0,
  "unit": "nanosecond",
  "attributes": {}
}
```

No file or folder name, path, document ID, engine ID, operation handler, item
type, extension, or other item attribute is attached.

### Synchronization size

```json
{
  "timestamp": 1787125986.04776,
  "trace_id": "72d875f54b31447fac8c03fffdef5e06",
  "span_id": "a708f04c71b283ac",
  "name": "drive.sync.size",
  "type": "distribution",
  "value": 1048576.0,
  "unit": "byte",
  "attributes": {}
}
```

One size sample is emitted with each duration sample. File values are the item
size in bytes; folders normally have value `0`. The two numeric samples contain
no item attributes.

### Direct Edit duration

```json
{
  "timestamp": 1787125986.047959,
  "trace_id": "72d875f54b31447fac8c03fffdef5e06",
  "span_id": "a708f04c71b283ac",
  "name": "drive.direct_edit.duration",
  "type": "distribution",
  "value": 250.0,
  "unit": "millisecond",
  "attributes": {
    "action": "open",
    "extension": ".pdf",
    "sentry.sdk.name": "sentry.python",
    "sentry.sdk.version": "2.44.0",
    "sentry.environment": "production",
    "sentry.release": "6.0.0"
  }
}
```

`action` is `open` or `edit`. `extension` is the lowercase suffix, including
the leading period; files without a suffix use `unknown`. The filename is not
sent.

### Direct Transfer size

```json
{
  "timestamp": 1787125986.048,
  "trace_id": "72d875f54b31447fac8c03fffdef5e06",
  "span_id": "a708f04c71b283ac",
  "name": "drive.direct_transfer.size",
  "type": "distribution",
  "value": 1048576.0,
  "unit": "byte",
  "attributes": {
    "type": "file",
    "sentry.sdk.name": "sentry.python",
    "sentry.sdk.version": "2.44.0",
    "sentry.environment": "production",
    "sentry.release": "6.0.0"
  }
}
```

`type` is `file` or `folder`.

## Engine gauge payload template

All eight engine gauges use the common payload shape below. Substitute `name`
and `value` with any engine metric from the inventory table.

```json
{
  "timestamp": 1787125986.048022,
  "trace_id": "72d875f54b31447fac8c03fffdef5e06",
  "span_id": "a708f04c71b283ac",
  "name": "drive.engine.sync_files",
  "type": "gauge",
  "value": 120.0,
  "unit": null,
  "attributes": {
    "sentry.sdk.name": "sentry.python",
    "sentry.sdk.version": "2.44.0",
    "sentry.environment": "production",
    "sentry.release": "6.0.0"
  }
}
```

Disabling **Allow advanced analytics** stops all metrics listed on this page.
Error events remain independently controlled by **Allow anonymous bug
reports**.
