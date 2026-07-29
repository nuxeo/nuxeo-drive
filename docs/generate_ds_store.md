# Generating the DMG `.DS_Store`

`tools/osx/generate-dmg-ds-store.sh` (re)generates the Finder layout (window
size, background picture, icon positions) used for the macOS `.dmg` installer,
and saves the resulting `.DS_Store` file under version control so it can be
reused later by the CI packaging job (`tools/osx/deploy_ci_agent.sh`), which
does not require a graphical session.

The script only handles **one branding at a time**. Which branding it targets
is controlled by a handful of hardcoded values at the top of the script
(`VOLUME_NAME`, `BACKGROUND_FILE`, `GENERATED_DS_STORE`, `PACKAGE_PATH`).

## Prerequisites

1. You must be logged into an active **graphical (GUI) session** on the Mac —
   this cannot be run over SSH/a headless session, since it drives Finder via
   `osascript`/AppleScript.
2. The app bundle referenced by `PACKAGE_PATH` must already exist under
   `dist/`. Build it first with PyInstaller, e.g.:

   ```bash
   ./venv/bin/python -OO -m PyInstaller alfresco.spec --clean --noconfirm
   # or, for the Nuxeo flavor:
   ./venv/bin/python -OO -m PyInstaller ndrive.spec --clean --noconfirm
   ```

3. Don't switch away from the Finder window that pops up while the script
   runs — let the `close`/`open`/`delay` sequence at the end finish on its
   own.

## Values per branding

| Value | Nuxeo | Alfresco |
| --- | --- | --- |
| `VOLUME_NAME` | `Nuxeo Drive` | `Hyland Drive for Alfresco` |
| `BACKGROUND_FILE` | `dmgbackground_nuxeo.png` | `dmgbackground_alfresco.png` |
| Background image dimensions (px) | 1210 × 720 | 836 × 264 |
| `GENERATED_DS_STORE` | `generated_DS_Store_nuxeo` | `generated_DS_Store_alfresco` |
| `DMG_TEMP` | `nuxeo-drive.tmp.dmg` | `alfresco-drive.tmp.dmg` |
| `PACKAGE_PATH` (under `dist/`) | `Nuxeo Drive.app` | `Hyland Drive for Alfresco.app` |
| Finder window bounds (`set the bounds of container window`) | `{100, 100, 700, 380}` | `{100, 100, 700, 350}` |
| App icon position (`set position of item "<app>.app"`) | `{150, 125}` | `{150, 100}` |
| Applications symlink position (`set position of item "Applications"`) | `{450, 125}` | `{450, 100}` |

### Window bounds and icon vertical positioning

The Finder window bounds and the icon `Y` coordinate are **not the same for
both flavors** — they depend on the background image being used, because the
background is scaled/anchored differently by Finder depending on the image's
pixel dimensions (see the table above). Verified visually:

- **Nuxeo** (`dmgbackground_nuxeo.png`, 1210 × 720): window bounds
  `{100, 100, 700, 380}` (content area 600 × 280) with icon `Y = 125` centers
  both icons vertically on the background.
- **Alfresco** (`dmgbackground_alfresco.png`, 836 × 264): window bounds
  `{100, 100, 700, 350}` (content area 600 × 250) with icon `Y = 100` centers
  both icons vertically on the background.

The icon size is 128 in both cases.

If you replace either background image with one of different dimensions, both
the window bounds and the icon Y coordinate may no longer be centered and will
need to be re-tuned by eye against the new image before committing the
regenerated `.DS_Store`.

These values must stay consistent with:

- The `CFBundleName`/`BUNDLE(name=...)` set in `ndrive.spec`/`alfresco.spec`
  (this is what actually gets built into `dist/`).
- The `generated_DS_Store_${flavor}` naming read by `deploy_ci_agent.sh` when
  building the final signed DMG.

To (re)generate the layout for the other flavor, update `VOLUME_NAME`,
`BACKGROUND_FILE`, `GENERATED_DS_STORE`, `DMG_TEMP`, `PACKAGE_PATH` **and the
`set the bounds of container window` value plus the two icon `set position`
Y coordinates in the embedded AppleScript** in
`tools/osx/generate-dmg-ds-store.sh` to the values from the table above before
running it.

## Steps

```bash
cd /path/to/nuxeo-drive

# 1. Build the app bundle for the desired flavor (see Prerequisites above).

# 2. Run the script (values in the script must match the flavor you built).
bash tools/osx/generate-dmg-ds-store.sh
```

On success, the script mounts a temporary disk image, opens it in Finder,
positions the icons and background, then copies the resulting `.DS_Store` to
`tools/osx/generated_DS_Store_<flavor>` before ejecting and deleting the
temporary image. Commit the updated `generated_DS_Store_<flavor>` file.

## Troubleshooting

- **`hdiutil: create failed - No space left on device`**: the disk image size
  is computed from the actual size of `dist/` plus a small buffer, so this
  usually means `dist/` contains more than just the app bundle (e.g. a leftover
  PyInstaller `COLLECT` folder). Clean out anything under `dist/` other than
  the `.app` bundle and rebuild if needed.
- **`Finder got an error: Can't set item "..." ... (-10006)`**: this is a
  generic/misleading Finder scripting error that most commonly means the named
  item does not actually exist on the mounted volume — i.e. `PACKAGE_PATH`
  does not point to a real app bundle in `dist/`. Double-check the app was
  built and that `PACKAGE_PATH` matches its exact name (including spaces).
- If a previous run failed partway through, the temporary volume may still be
  mounted and the temp `.dmg` may still exist. Clean up before retrying:

  ```bash
  hdiutil detach "/Volumes/<VOLUME_NAME>" -force
  rm -f tools/osx/<DMG_TEMP filename>
  ```
