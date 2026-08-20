# Sentry data collection

This page is the data inventory for Sentry telemetry sent by Nuxeo Drive. It
covers the application configuration in `nxdrive/drive/tracing.py` and the
default integrations enabled by `sentry-sdk==2.44.0`.

The exact contents of an event depend on the failure and the activity that
preceded it. Fields described as conditional are collected only when the
corresponding data or integration is present.

## Collection controls

### First-run metric

On a new installation, Drive increments the `drive.first_run` Sentry counter by
one regardless of the error-reporting and advanced-analytics choices. It has
only these attributes:

- Drive application version.
- Drive server type: `NUXEO` or `ALFRESCO`.
- Full operating-system name and version.
- A random user ID generated as a UUID when the metric is created.

The random user ID is included as the metric's `user.id` attribute. It is not
stored in the configuration database or reused. Before sending, Drive removes
automatic SDK metric attributes such as the environment, SDK name, and SDK
version, retaining only the four attributes listed above. The metric protocol
also carries its fixed name and type, the value `1`, a timestamp, and random
trace and span identifiers.

Drive initializes Sentry only for this metric, flushes it, and then closes and
detaches the temporary client. Successful capture does not mark Sentry as
initialized for ongoing telemetry.

The metric is eligible on fresh Nuxeo and Alfresco installations. Existing
Nuxeo installations whose immutable `original_version` is earlier than the
Nuxeo rollout version in `nxdrive/__init__.py` are also eligible. Alfresco is a
pilot release, so existing Alfresco installations are not treated as legacy
installations for this metric.

After successful capture, Drive stores the UTC completion time in
`sentry_first_run_metric_sent_at`. A second attempt is never made when this
marker exists. The former
`sentry_first_run_event_sent` marker is still honored to avoid duplicates on
installations that already emitted the metric.

Failed delivery is retried on a later startup because no sent marker is stored.
A crash after Sentry accepts the metric but before Drive persists `sent_at` can
therefore create a duplicate. True exactly-once delivery would require
server-side idempotency, which Sentry metrics do not provide here. This tradeoff
is accepted for this telemetry.

`SKIP_SENTRY=1` and an empty `SENTRY_DSN` remain hard operational overrides and
prevent delivery. An overridden or failed delivery remains eligible for retry
on a later startup.

### User-controlled telemetry

Apart from the first-run metric, Sentry is not initialized for ongoing telemetry
until the user enables **Allow anonymous bug reports** or **Allow advanced
analytics** in the first-run consent dialog or in Settings. After consent,
initialization is still skipped when either of these conditions is met:

- `SKIP_SENTRY=1` is set.
- `SENTRY_DSN` is set to an empty value.

Disabling both telemetry choices closes and detaches the active Sentry client.

### Fatal error dialog

The Fatal Error window includes a **Send error to Hyland** button. Clicking it
sends that single failure even when persistent error reporting is disabled. The
button does not change `Options.use_sentry`, `Options.use_analytics`, the
configuration database, or `metrics.state`.

If Sentry is not already active, Drive initializes it only for this capture,
sends and flushes the event, and then closes that temporary client. If Sentry is
already active, the existing client is reused. `SKIP_SENTRY=1` and an empty
`SENTRY_DSN` remain hard operational overrides.

The event uses the same privacy settings as normal bug reporting. It includes
the exception type, message, structured traceback, source context, runtime/OS
context, and up to 20 recent Drive log lines as breadcrumbs. Frame-local values
remain disabled by `include_local_variables=False`. If no active exception is
available, Drive sends the formatted traceback text as fallback diagnostic
data.

The DSN can be changed with `SENTRY_DSN`, and the environment can be changed
with `SENTRY_ENV`. The default environment is `production`.

Every Sentry initialization adds the active Drive server type as the
`drive.server` tag. Its value is `NUXEO` or `ALFRESCO`.

Error events are discarded when `Options.use_sentry` is false. This option is
false by default and can be changed through the persisted error-reporting
preference. Error events with the same stack filenames and line numbers are
sent only once per application process.

Advanced analytics metrics are emitted only when `Options.use_analytics` is
true. Enabling advanced analytics initializes the Sentry SDK but does not allow
error events; error reporting remains controlled independently by
`Options.use_sentry`.

Both the first-run consent dialog and the Settings switches update the live
options, the `use_sentry` and `use_analytics` configuration-database values, and
the `metrics.state` file. Changes take effect immediately and persist across
restarts. The database values are authoritative when both persistence stores
exist; startup repairs `metrics.state` to match them. For an older installation
that has only `metrics.state`, startup imports both choices into the database.
A persisted opt-in initializes Sentry during Manager startup; on first launch,
initialization occurs only after the dialog has closed with at least one choice
selected.

Sentry's logging integration is explicitly configured to keep `INFO` and
higher records as breadcrumbs and send `ERROR` and `CRITICAL` records as
standalone events. This central boundary covers every `log.error()`,
`log.critical()`, and `log.exception()` call under `nxdrive/drive` without
adding capture calls to each handler. Because the integration is process-wide,
it can also collect records from dependencies and other Python loggers unless
Sentry excludes that logger. `WARNING` records remain breadcrumbs and are not
sent as standalone events at this stage.

The `before_send` callback performs only consent checking and duplicate
suppression. It does not remove or redact fields. It is applied to error events,
not performance transactions. Performance tracing is disabled when only error
reporting is enabled. When advanced analytics is enabled, performance sampling
is configured at 100% with `traces_sample_rate=1.0`; therefore, any transactions
created by the application or an enabled integration are eligible to be sent.

## Data included in error events

### Event metadata

- A randomly generated Sentry event ID.
- Event timestamp.
- Event level or severity.
- Platform identifier, normally `python`.
- Sentry SDK name and version.
- Application release/version.
- Deployment environment, defaulting to `production`.
- Hostname in Sentry's `server_name` field.
- Trace identifiers and trace context.
- Transaction information associated with the event, when available.

### Exception details

- Exception type.
- Exception module.
- Exception message/value.
- Exception handling mechanism.
- Chained exceptions, when present.

### Stack frames

For every captured exception frame, Sentry can include:

- Filename and absolute source path.
- Python module and function name.
- Source line number.
- Current source-code line.
- Source-code lines before and after the current line.
- Whether the frame is classified as application code.

A plain `log.error()` or `log.critical()` call has no active exception payload.
Because `attach_stacktrace=True`, its event instead includes the current thread
and stack frames at the logging call. A `log.exception()` call made inside an
exception handler includes the active exception and its traceback.

Local-variable collection is explicitly disabled with
`include_local_variables=False`. Stack frames therefore do not include their
`vars` mappings, reducing the risk of sending tokens, credentials, document
metadata, request data, or file-content fragments that happened to be in scope
when an error occurred. Paths and other sensitive values can still appear in
exception messages, log messages, command-line arguments, or breadcrumbs.

### Runtime and operating-system context

Nuxeo Drive explicitly adds:

- Runtime name: `Python`.
- Full Python version.
- Operating-system name.
- Full operating-system version.

The SDK also attaches trace context generated for the event.

### Process and dependency data

The enabled SDK defaults add:

- The process command-line arguments from `sys.argv`.
- Names and versions of imported or installed Python packages.

Command-line arguments may contain file paths, server addresses, option values,
or other data provided when the application was started.

### Breadcrumbs and logs

Up to 100 breadcrumbs preceding an event can be included. Depending on activity,
a breadcrumb can contain:

- Timestamp, type, category, and level.
- Log message and logger name.
- Structured data attached to the log record.
- Thread name and thread identifier.
- Standard-library activity recorded by the SDK.
- Boto3/AWS operation details when Boto3 is used.

The logging integration records `INFO`, `WARNING`, `ERROR`, and `CRITICAL`
entries as breadcrumbs. It also turns `ERROR` and `CRITICAL` records into
standalone Sentry events. Consequently, values written to application logs can
also reach Sentry. Exception tracebacks and associated stack data can accompany
those log events.

### Performance transactions

When a transaction or span is created, Sentry can collect:

- Trace, transaction, and span identifiers.
- Transaction and operation names.
- Parent-child span relationships.
- Start times, end times, and durations.
- Status and error state.
- Span descriptions and integration-specific data.
- Measurements and performance metadata, when supplied.
- Boto3 or supported standard-library operation timing, when instrumented.

With advanced analytics enabled, the application configures a sample rate of
`1.0`, meaning 100% of created transactions are sampled. With error reporting
alone, `traces_sample_rate=None` disables tracing. This does not mean that
Sentry continuously records the desktop or every application operation; a
transaction must first be created by application code or an enabled
integration.

## Advanced analytics metrics

When **Allow advanced analytics** is enabled, Nuxeo Drive sends these native
Sentry metrics. See [Sentry advanced analytics metrics](sentry_metrics.md) for
every concrete metric name and example payload values.

| Metric | Type | Value and attributes |
| --- | --- | --- |
| `drive.sync.duration` | Distribution | Synchronization duration in nanoseconds. No item attributes are sent. |
| `drive.sync.size` | Distribution | Synchronized item size in bytes. No item attributes are sent. |
| `drive.direct_edit.duration` | Distribution | Direct Edit open/edit duration in milliseconds, with the action and lowercase file extension as attributes. The filename is not sent. |
| `drive.direct_transfer.size` | Distribution | Completed transfer size in bytes, with the file or folder type as an attribute. |
| `drive.engine.<stat>` | Gauge | Integer engine statistics such as synchronized files/folders, errors, conflicts, active synchronization, and total file size. |

Engine statistics are collected when the analytics worker starts and then once
per hour. Synchronization, Direct Edit, and Direct Transfer metrics are emitted
when those operations complete. Disabling advanced analytics stops all four
metric families.

## Enabled default integrations

With the dependencies currently installed, Sentry enables these integrations:

| Integration | Data or behavior |
| --- | --- |
| `ArgvIntegration` | Adds process command-line arguments. |
| `AtexitIntegration` | Flushes queued events when the process exits; it does not add an application data category. |
| `Boto3Integration` | Adds error and performance context for instrumented Boto3/AWS operations. |
| `DedupeIntegration` | Suppresses duplicate exception events; it does not add an application data category. |
| `ExcepthookIntegration` | Captures otherwise unhandled main-thread exceptions. |
| `LoggingIntegration` | Collects `INFO+` breadcrumbs and sends `ERROR+` records as events. |
| `ModulesIntegration` | Adds Python package/module versions. |
| `StdlibIntegration` | Adds supported Python standard-library breadcrumbs and performance spans. |
| `ThreadingIntegration` | Captures otherwise unhandled thread exceptions and their thread context. |

The set of automatically enabled integrations can change when the SDK version
or installed dependencies change.

## Data not intentionally configured

Nuxeo Drive does not explicitly set or upload the following through Sentry:

- A Sentry user ID, user name, or email address.
- Custom user attributes.
- Custom application tags.
- The synchronization database.
- Complete synchronized files or folders.
- Screenshots, screen recordings, or keyboard input.
- Browser cookies or a web request body in an ordinary desktop exception.

No user or HTTP request object was present in a representative desktop
exception event generated with the current SDK configuration. This is not an
absolute exclusion: data from the list above can still appear indirectly in an
exception message, log message, command-line argument, source path, breadcrumb,
or local variable. Sentry's receiving infrastructure can also observe normal
network metadata, including the source IP address of the connection.

## Maintenance

This is a living data inventory. Update it in the same change whenever work
modifies any of the following:

- Arguments passed to `sentry_sdk.init()`.
- Sentry SDK version or default integrations.
- Calls that capture events, messages, logs, transactions, or spans.
- Scope contexts, tags, user information, attachments, or breadcrumbs.
- Consent, sampling, filtering, deduplication, or redaction behavior.
- Application dependencies that cause another Sentry integration to be enabled.

When updating this page, verify the effective SDK options and integrations in
the project's selected Python environment rather than relying only on SDK
documentation or defaults from another version.
