# Open-file detection helper (`check_open`)

macOS-only. Lets Drive hold back a download while the user still has the local
file open, instead of overwriting what they are working on.

## What it is

A small Swift command-line tool. Source and build script live in
`tools/osx/utilities/`; the compiled universal binary is committed at
`nxdrive/drive/data/utilities/check_open`.

| Path | Role |
|---|---|
| `tools/osx/utilities/check_open.swift` | Source — the only thing to edit |
| `tools/osx/utilities/build_check_open.sh` | Builds arm64 + x86_64 and `lipo`s them together |
| `nxdrive/drive/data/utilities/check_open` | Committed binary, consumed at runtime |

### Why a separate binary

The checks it performs are not reachable from Python in a packaged build. The
kernel check needs `lsof` semantics with the caller's own process excluded, and
the window-inspection tiers need the Accessibility APIs, which PyObjC does not
expose in the frozen application.

## Modes

```bash
check_open <path>            # TRUE / FALSE — is the file open by another process?
check_open --check-permission    # GRANTED / DENIED, without prompting
check_open --request-permission  # GRANTED / DENIED, prompting if needed
```

The kernel check always runs. The three window/title tiers run only when
Accessibility permission has been granted, so a refusal degrades detection
rather than disabling it.

## How Drive handles the permission

`--request-permission` returns as soon as the system dialog is shown, long
before the user answers it, so its result cannot be trusted as the outcome.
The grant is also made and withdrawn in System Settings, which tells a
command-line helper nothing.

Drive therefore never remembers the answer:

* `--check-permission` is run on every engine start, so a grant made outside
  the application is picked up on the next launch;
* `--request-permission` is shown at most once, recorded in the DAO config key
  `open_file_permission_asked`, so a refusal does not nag on every start;
* switching the Synchronization feature on shows the prompt again, because an
  explicit user action is worth re-asking for.

All of this runs on the engine thread pool — the probe spawns a process, and
the feature toggle arrives on the GUI thread.

## Building

```bash
./tools/osx/utilities/build_check_open.sh
```

Requires the Swift toolchain (Xcode or the Command Line Tools). The script
builds both slices at `-target {arch}-apple-macos11.0`, merges them with
`lipo`, writes the result to `nxdrive/drive/data/utilities/check_open` and marks
it executable. Verify with:

```bash
lipo -archs nxdrive/drive/data/utilities/check_open   # x86_64 arm64
```

## How it reaches a release

`build_alfresco_installer()` in `tools/posix/deploy_ci_agent.sh` runs the build
script **before** PyInstaller whenever `OSI` is `osx`, so the bundled helper is
always compiled from the `check_open.swift` in that same commit.

PyInstaller then picks it up through the existing `(data, "data")` mapping in
`alfresco.spec` — no spec entry of its own is needed, because the helper lives
under `nxdrive/drive/data/`. `tools/cleanup_application_tree.py` works from a
removal list rather than a keep list, so it is not stripped from `dist/`.

Signing happens after the freeze, so the helper is signed along with the rest of
the bundle.

### Why the binary is committed as well

So that a developer running from source, or building on a machine without the
Swift toolchain, still gets the feature. The release build recompiles it
regardless, so the committed copy can never silently become what ships.

**If you edit `check_open.swift`, run the build script and commit the rebuilt
binary in the same change.** Nothing fails if you forget — the release will be
correct either way — but local runs would keep using the stale copy.

## Runtime behaviour

`DarwinIntegration` locates the helper with
`find_resource("utilities", file="check_open")` and caches the result. It
re-applies the executable bit on first use, because PyInstaller does not
preserve it for data files.

If the helper is missing or unusable, `has_file_open_detection()` returns
`False` and Drive downloads as it did before — the feature is skipped, never
fatal.

## Troubleshooting

| Symptom in the log | Meaning |
|---|---|
| `Open-file detection disabled: ... is missing` | The helper was not found. Run the build script. |
| `Accessibility permission not granted yet; open-file detection will use the kernel check until it is` | Expected until the user grants it. Kernel detection still works, and the grant is re-read on the next start. |
| `check_open timed out` | The probe exceeded its timeout; treated as "unknown" and the download proceeds. |
| No `File open locally` line ever appears | Normal for editors that do not hold the file open. TextEdit reads and closes immediately; Word, Excel and `tail -f` are detected. |
