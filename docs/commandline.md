# Command Line Interface

Drive ships a `git`-style command line: an optional global set of flags,
followed by an optional subcommand and its own flags. When no subcommand is
given, the graphical application is started along with the synchronization
process.

The CLI is defined in [`nxdrive/drive/commandline.py`](../nxdrive/drive/commandline.py)
(`CliHandler.make_cli_parser`).

> **Nuxeo vs. non-Nuxeo builds** — Some subcommands and flags are only
> registered when the active build targets a Nuxeo server (see the
> `if Options.server_type == "NUXEO":` guards in `make_cli_parser`).
> Availability is called out in each section below and summarized at the
> [end of this document](#availability-summary).

Throughout the examples we use `ndrive` as the binary name. On other builds,
substitute the platform binary — e.g. on macOS Alfresco:

```bash
APP="/Applications/Hyland Drive for Alfresco.app/Contents/MacOS/alfresco-drive"
```

---

## Top-level invocation

Running the binary with no subcommand starts the GUI (or the console app if
`console` is passed) and, once bootstrapped, the sync loop:

```bash
ndrive
```

The `-v` / `--version` flag short-circuits everything and prints the version:

```bash
ndrive --version
ndrive -v
```

---

## Common (global) flags

These flags are accepted on the top-level parser **and** on every subcommand,
regardless of position. They come from `common_parser` in
`make_cli_parser`.

### Available on every build

| Flag | Purpose |
|---|---|
| `--nxdrive-home PATH` | Folder that stores the app configuration and logs (defaults to `Options.nxdrive_home`). |
| `--log-level-console {DEBUG,INFO,WARNING,ERROR}` | Minimum log level printed to the console. |
| `--log-level-file {DEBUG,INFO,WARNING,ERROR}` | Minimum log level written to file. |
| `--log-filename PATH` | Log file path. Defaults to `<nxdrive-home>/logs/<server-type>.log`. |
| `--debug` | Fires a post-mortem debugger on uncaught errors and enables extra REST API parameter checks. |
| `--sync-and-quit` | Wait for the first successful sync pass, then quit. |
| `-v`, `--version` | Print the current version and exit. |

Example combining several flags:

```bash
ndrive --log-level-console DEBUG --log-level-file DEBUG --debug --sync-and-quit
```

### Nuxeo-only

| Flag | Purpose |
|---|---|
| `--locale CODE` | Default UI language (`en`, `fr`, …). |
| `--force-locale CODE` | Force the UI language, overriding user preference. |
| `--update-site-url URL` | Auto-update site URL. |
| `--channel {alpha,beta,release,centralized}` | Update channel. |
| `--nofscheck` | Skip the standard filesystem binding check (e.g. for network filesystems). |
| `--proxy-server URL` | Proxy server, e.g. `http://user:pw@host:port`. |
| `--ssl-no-verify` | Accept invalid or custom SSL certificates (unsafe). |
| `--debug-pydev` | Attach to a PyDev remote debugger. |
| `--delay SECS` | Delay in seconds between remote polls. |
| `--handshake-timeout SECS` | HTTP timeout for the handshake request. |
| `--timeout SECS` | HTTP timeout for sync Automation calls. |
| `--update-check-delay SECS` | Delay between auto-update checks. |
| `--max-errors N` | Maximum retries before giving up on a file in error. |

Example (Nuxeo build):

```bash
ndrive --proxy-server http://proxy.example.com:3128 \
       --ssl-no-verify \
       --delay 60 \
       --max-errors 5
```

---

## Subcommands

### `bind-server` — attach a local folder to a server *(all builds)*

Registers an account: creates an engine that maps a local folder to a remote
server. If `--password` is omitted, the credentials are not verified at bind
time (`check_credentials=False`).

**Positional arguments (required, in order)**

1. `username`
2. `server_url`

**Options**

| Flag | Default | Notes |
|---|---|---|
| `--password PASSWORD` | *(unset)* | If omitted, credentials are not verified. |
| `--local-folder PATH` | Platform default (`get_default_local_folder()`) | Where synchronized workspaces are stored. |
| `--remote-repo NAME` | `Options.remote_repo` (usually `default`) | Nuxeo/Alfresco repository name. |

> **Note.** The local folder must exist before binding — the bind flow will
> try to set an extended attribute (folder icon) on it and fail with
> `FileNotFoundError` if it does not exist. Create it up-front:
>
> ```bash
> mkdir -p ~/AlfrescoDrive
> ```

**Examples**

Minimal (no password ⇒ no credential check):

```bash
ndrive bind-server jdoe https://demo.example.com/nuxeo
```

With password and custom local folder:

```bash
mkdir -p ~/AlfrescoDrive
ndrive bind-server \
    --password "s3cret" \
    --local-folder ~/AlfrescoDrive \
    admin@example.com https://acs.example.com/
```

With a custom repository:

```bash
ndrive bind-server \
    --password "s3cret" \
    --remote-repo default \
    jdoe https://demo.example.com/nuxeo
```

---

### `unbind-server` — detach from a remote server *(all builds)*

Locates the engine whose local folder matches `--local-folder` and removes
it. No network call is made.

**Options**

| Flag | Default |
|---|---|
| `--local-folder PATH` | Platform default. |

Exit codes:
- `0` — engine was found and removed.
- `1` — no engine registered for that local folder (a warning is logged).

**Example**

```bash
ndrive unbind-server --local-folder ~/AlfrescoDrive
```

---

### `bind-root` — register a remote folder as a sync root *(Nuxeo only)*

Registers a remote document (path or id reference) as a synchronization root
on an already-bound engine.

**Positional**: `remote_root` (remote path or document id).

**Options**

| Flag | Default | Notes |
|---|---|---|
| `--local-folder PATH` | Platform default | Must match a folder already bound via `bind-server`. |
| `--remote-repo NAME` | `Options.remote_repo` | Repository containing `remote_root`. |

**Examples**

By path:

```bash
ndrive bind-root /default-domain/workspaces/MyWorkspace \
    --local-folder ~/NuxeoDrive
```

By document id:

```bash
ndrive bind-root 12345678-abcd-ef01-2345-6789abcdef01 \
    --local-folder ~/NuxeoDrive \
    --remote-repo default
```

---

### `unbind-root` — unregister a sync root *(Nuxeo only)*

Reverse of `bind-root`. Same positional / options.

```bash
ndrive unbind-root /default-domain/workspaces/MyWorkspace \
    --local-folder ~/NuxeoDrive
```

---

### `console` — run without GUI *(Nuxeo only)*

Runs the sync engine in headless mode. Useful for servers, CI, and cron.
Accepts all common flags. Combines naturally with `--sync-and-quit`.

```bash
ndrive console --log-level-console INFO
ndrive console --sync-and-quit
ndrive console --debug-pydev
```

---

### `clean-folder` — remove xattrs from a folder *(Nuxeo only)*

Recursively removes Drive extended attributes from `--local-folder`. Useful
after uninstalling or when moving a Drive folder to a different account.

**Options**

| Flag |
|---|
| `--local-folder PATH` *(required in practice — the command prints "A folder must be specified" and exits `1` if missing)* |

```bash
ndrive clean-folder --local-folder ~/NuxeoDrive
```

---

### `uninstall` — remove app data *(Nuxeo only)*

Delegates to the platform integration's `uninstall()` (see
`AbstractOSIntegration.uninstall`). This does **not** stop other engines or
touch synced files; it clears Drive's own app data.

```bash
ndrive uninstall
```

---

### Context-menu subcommands *(Nuxeo only)*

These are the callbacks wired to the OS shell integration. They are usually
invoked by the OS, not directly by the user, but can be run manually for
testing.

| Subcommand | Purpose | Flag |
|---|---|---|
| `access-online` | Open the document in the browser. | `--file PATH` |
| `copy-share-link` | Copy the document's share-link to the clipboard. | `--file PATH` |
| `edit-metadata` | Open the metadata window for a file. | `--file PATH` |
| `direct-transfer` | Direct Transfer of a file to the server. | `--file PATH` |

Examples:

```bash
ndrive access-online     --file ~/NuxeoDrive/Workspaces/report.pdf
ndrive copy-share-link   --file ~/NuxeoDrive/Workspaces/report.pdf
ndrive edit-metadata     --file ~/NuxeoDrive/Workspaces/report.pdf
ndrive direct-transfer   --file ~/Desktop/big-video.mp4
```

Behind the scenes, `direct-transfer` crafts a `nxdrive://direct-transfer/…`
protocol URL and hands it to a (possibly newly started) running instance —
see the "Protocol URL handoff" section below.

---

## Protocol URL handoff (not a subcommand)

Any argument that starts with `nxdrive:` (case-insensitive) is intercepted
by `parse_cli`, stored on `Options.protocol_url`, and forwarded to a running
instance over a local socket. If no instance is running, one is started and
the URL is processed at launch time.

Typical invocations (usually done by the OS URL handler, not humans):

```bash
ndrive "nxdrive://token/abc123..."
ndrive "nxdrive://direct-transfer//Users/me/file.pdf"
```

The token URL is redacted in logs (see `CliHandler.redact_payload`).

---

## Recipes

### Fresh setup on macOS (Alfresco build)

```bash
APP="/Applications/Hyland Drive for Alfresco.app/Contents/MacOS/alfresco-drive"

# 0) Ensure the local folder exists (bind won't create it)
mkdir -p ~/AlfrescoDrive

# 1) Bind the server
"$APP" bind-server \
    --password "s3cret" \
    --local-folder ~/AlfrescoDrive \
    admin@example.com https://acs.example.com/

# 2) Launch the GUI (or use --sync-and-quit for a headless one-shot)
"$APP" --sync-and-quit
```

### Cron / CI: one-shot headless sync (Nuxeo build only)

```bash
ndrive console --sync-and-quit --log-level-file INFO
```

### Enable synchronization

Sync enablement is a **feature flag**, not a CLI switch. Toggle it via
`config.ini` under `<nxdrive-home>` and restart:

```ini
[DEFAULT]
env = prod

[prod]
feature.synchronization = true
```

A restart is required for the change to take effect. See
[configuration.md](configuration.md) for the full list of feature flags.

---

## Availability summary

### Non-Nuxeo builds (e.g. Alfresco Drive)

**Subcommands available**

- `bind-server`
- `unbind-server`
- *(no subcommand)* → GUI launch

**Common flags available**

- `--nxdrive-home`
- `--log-level-console`
- `--log-level-file`
- `--log-filename`
- `--debug`
- `--sync-and-quit`
- `-v`, `--version`

### Nuxeo-only

**Subcommands**

- `bind-root`, `unbind-root`
- `console`
- `clean-folder`
- `uninstall`
- `access-online`, `copy-share-link`, `edit-metadata`, `direct-transfer`

**Common flags**

- `--locale`, `--force-locale`
- `--update-site-url`, `--channel`
- `--nofscheck`
- `--proxy-server`
- `--ssl-no-verify`
- `--debug-pydev`
- `--delay`, `--handshake-timeout`, `--timeout`, `--update-check-delay`
- `--max-errors`

### Exit codes

Most subcommands return:

- `0` — success
- `1` — expected failure (e.g. "no engine registered for local folder", or a
  missing required argument such as `--local-folder` for `clean-folder`)

Unexpected errors bubble up as tracebacks and, when `--debug` is set, drop
you into a post-mortem debugger.
