# Alfresco: Disabled / Overridden UI Sections

This document tracks UI elements, links, and strings that were **hidden, disabled, or altered** specifically for the `ALFRESCO` server type (`Options.server_type == "ALFRESCO"`).

Use this as the checklist when re-enabling these sections (e.g. once Alfresco-specific
targets — docs, feedback portal, help — become available).

The server type is exposed to QML via the `SERVER_TYPE` context property, set in
[`nxdrive/drive/gui/application.py`](../nxdrive/drive/gui/application.py) from `Options.server_type`.

---

## 1. About tab — application name in license text

**File:** [`nxdrive/drive/data/qml/AboutTab.qml`](../nxdrive/drive/data/qml/AboutTab.qml)

The license paragraph mentioned the hard-coded string `Nuxeo Drive` in three places.
A local `appName` property now switches between:

- `NUXEO`  → `Nuxeo Drive`
- `ALFRESCO` → `Hyland Drive for Alfresco`

```qml
property string appName: SERVER_TYPE === "ALFRESCO" ? "Hyland Drive for Alfresco" : "Nuxeo Drive"
```

**To revert:** replace `appName` references with the literal `"Nuxeo Drive"` and drop the property.

---

## 2. About tab — `FEEDBACK_LINK` hidden for Alfresco

**File:** [`nxdrive/drive/data/qml/AboutTab.qml`](../nxdrive/drive/data/qml/AboutTab.qml)

The "Something is missing? Share your feedback here." link points at a Nuxeo
ProdPad portal (`https://portal.prodpad.com/089ed2a6-c892-11e7-aea6-0288f735e5b9`).
It is hidden when running as Alfresco:

```qml
IconLink {
    visible: SERVER_TYPE !== "ALFRESCO"
    text: qsTr("FEEDBACK_LINK") + tl.tr
    ...
}
```

**To re-enable:** remove the `visible:` binding, or point at an Alfresco-specific feedback URL.

---

## 3. Systray menu — `HELP` item hidden for Alfresco

**File:** [`nxdrive/drive/data/qml/SystrayMenu.qml`](../nxdrive/drive/data/qml/SystrayMenu.qml)

The systray "Help" entry calls `api.open_help()` which resolves to Nuxeo
documentation. It is hidden for Alfresco:

```qml
SystrayMenuItem {
    visible: SERVER_TYPE !== "ALFRESCO"
    text: qsTr("HELP") + tl.tr
    onClicked: {
        api.open_help()
        control.visible = false
    }
}
```

**To re-enable:** remove the `visible:` binding once `api.open_help()` handles the
Alfresco case (or route it to Alfresco docs).

---

## 4. Release notes dialog — Alfresco-specific message

**Files:**
- Python: [`nxdrive/drive/gui/application.py`](../nxdrive/drive/gui/application.py) — `Application._show_release_notes`
- i18n reference: [`nxdrive/drive/data/i18n/i18n.json`](../nxdrive/drive/data/i18n/i18n.json)
- i18n Crowdin source: [`nxdrive/data/i18n/i18n.json`](../nxdrive/data/i18n/i18n.json)

The default `RELEASE_NOTES_MSG` contains a link to the Nuxeo release-notes page
(`https://doc.nuxeo.com/n/Bm2`). For Alfresco a new key `RELEASE_NOTES_MSG_ALFRESCO`
was added (without the Nuxeo link) and selected at runtime:

```python
msg_key = (
    "RELEASE_NOTES_MSG_ALFRESCO"
    if Options.server_type == "ALFRESCO"
    else "RELEASE_NOTES_MSG"
)
self.display_info(
    Translator.get("RELEASE_NOTES_TITLE", values=[APP_NAME]),
    msg_key,
    [APP_NAME, current],
)
```

Reference-locale entry added:

```json
"RELEASE_NOTES_MSG_ALFRESCO": "Your %1 has been correctly updated to the version <b>%2</b>."
```

**To revert:** drop the branch and use `"RELEASE_NOTES_MSG"` unconditionally; the
`RELEASE_NOTES_MSG_ALFRESCO` key can then be removed from the i18n files.

**Note on translations:** only the English reference files carry the new key.
Non-English locales fall back to English until Crowdin translations are added.

---

## Not disabled — already server-type aware

The following are **already** driven by `Options.server_type` / `download_urls.txt`
and require no further gating:

- **`UPDATES_LINK`** in `AboutTab.qml` — `api.get_update_url()` returns
  `Options.update_site_url`, which is populated from
  [`nxdrive/download_urls.txt`](../nxdrive/download_urls.txt) at launch (see
  [`nxdrive/drive/commandline.py`](../nxdrive/drive/commandline.py), around the
  `download_urls.txt` read).
