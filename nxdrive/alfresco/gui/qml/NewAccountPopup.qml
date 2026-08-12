import QtQuick
// QtQuick.Dialogs is available in Qt 6.2+
import QtQuick.Dialogs
import QtQuick.Layouts
import "../../../drive/data/qml/icon-font/Icon.js" as MdiFont
import "../../../drive/data/qml"

NuxeoPopup {
    id: control
    width: 480
    padding: 20

    title: qsTr("NEW_ENGINE") + tl.tr

    // Set to false once the server's Device Sync /config webscript
    // advertises ``enableBasicAuth: false``. Defaults to true so that
    // legacy Alfresco servers (which don't expose the capability at
    // all) keep working exactly like before.
    property bool serverAllowsBasicAuth: true
    // Guard so we don't spam the probe on every keystroke.
    property string _lastProbedUrl: ""

    function _refreshAuthCapabilities() {
        var url = urlInput.text
        if (!url || url === _lastProbedUrl)
            return
        // Only probe when the URL is syntactically valid — the input
        // has its own RegularExpressionValidator so ``acceptableInput``
        // is a cheap gate before hitting the network.
        if (!urlInput.acceptableInput)
            return
        _lastProbedUrl = url
        try {
            var raw = api.alfresco_probe_capabilities(url)
            if (!raw)
                return
            var caps = JSON.parse(raw)
            serverAllowsBasicAuth = caps.enable_basic_auth !== false
            if (!serverAllowsBasicAuth && useLegacyAuth.checked) {
                // Server refuses basic auth — force the browser flow.
                useLegacyAuth.checked = false
            }
        } catch (e) {
            // Never let a probe failure block the dialog.
            serverAllowsBasicAuth = true
        }
    }

    Component.onCompleted: {
        height = Qt.binding(function() {
            return popupContent.implicitHeight + topPadding + bottomPadding
        })
    }

    onOpened: {
        folderInput.text = api.default_server_local_folder()
        urlInput.focus = true
    }

    contentItem: ColumnLayout {
        id: popupContent
        spacing: 20

        ColumnLayout {
            id: formFields
            Layout.fillWidth: true
            Layout.topMargin: 30
            spacing: 20
            Keys.onReturnPressed: connectButton.clicked()
            Keys.onEnterPressed: connectButton.clicked()

            ColumnLayout {
                id: server_url
                Layout.fillWidth: true
                spacing: 10

                ScaledText { text: qsTr("URL") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: urlInput
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    lineColor: acceptableInput ? focusedUnderline : errorContent
                    inputMethodHints: Qt.ImhUrlCharactersOnly
                    KeyNavigation.tab: folderInput
                    placeholderText: "https://server.com"
                    text: api.default_server_url_value()
                    font.family: "Courier"
                    onAccepted: {
                        control._refreshAuthCapabilities()
                        connectButton.clicked()
                    }
                    onEditingFinished: control._refreshAuthCapabilities()
                    onActiveFocusChanged: {
                        if (!activeFocus)
                            control._refreshAuthCapabilities()
                    }
                    validator: RegularExpressionValidator { regularExpression: /^https?:\/\/[^\s<"\/]+(\/[^\s<"]*)?$/ }
                }
            }

            ColumnLayout {
                id: local_folder
                Layout.fillWidth: true
                spacing: 10

                RowLayout {
                    spacing: 10

                    ScaledText {
                        text: qsTr("ENGINE_FOLDER") + tl.tr
                        wrapMode: Text.WordWrap
                        Layout.maximumWidth: control.width / 3
                        Layout.preferredWidth: contentWidth
                        color: secondaryText
                    }
                    IconLabel {
                        Layout.alignment: Qt.AlignRight
                        icon: MdiFont.Icon.folderOutline
                        onClicked: fileDialog.open()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    spacing: 20

                    NuxeoInput {
                        id: folderInput
                        Layout.fillWidth: true
                        lineColor: focusedUnderline
                        onAccepted: connectButton.clicked()
                        onTextChanged: {
                            var disk_space = api.get_free_disk_space(folderInput.text)
                            freeSpace.text = qsTr("FREE_DISK_SPACE").arg(disk_space) + tl.tr
                        }
                    }
                    ScaledText {
                        id: freeSpace
                        visible: folderInput.text
                        color: secondaryText
                    }
                }
            }

            RowLayout {
                id: authMethodRow
                spacing: 10
                // The legacy ticket/basic auth path is only offered when
                // the Alfresco server advertises ``enableBasicAuth: true``
                // via its Device Sync /config webscript. On Alfresco Drive
                // 1.0-only deployments the server will report false and
                // the checkbox is hidden entirely — the browser flow is
                // then the sole option.
                visible: control.serverAllowsBasicAuth

                ScaledText {
                    text: qsTr("USE_LEGACY_AUTH") + tl.tr
                    color: mediumGray
                }
                NuxeoCheckBox {
                    id: useLegacyAuth
                    checked: true
                    leftPadding: 0
                }
            }

            Column {
                id: credentials
                Layout.fillWidth: true
                width: parent.width
                spacing: 10
                // Only shown for legacy (ticket/basic) authentication.
                // For modern OAuth2 the credentials are entered in the
                // browser, so the fields are hidden here. Also hidden
                // when the server disallows basic auth altogether.
                visible: control.serverAllowsBasicAuth && useLegacyAuth.checked

                ScaledText { text: qsTr("USERNAME") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: usernameInput
                    x: 25
                    width: parent.width - 25
                    height: Math.max(implicitHeight, 24)
                    placeholderText: "admin"
                    KeyNavigation.tab: passwordInput
                    onAccepted: connectButton.clicked()
                }

                ScaledText { text: qsTr("PASSWORD") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: passwordInput
                    x: 25
                    width: parent.width - 25
                    height: Math.max(implicitHeight, 24)
                    echoMode: TextInput.Password
                    KeyNavigation.tab: connectButton
                    onAccepted: connectButton.clicked()
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight

            NuxeoButton {
                text: qsTr("CANCEL") + tl.tr
                primary: false
                onClicked: control.close()
            }

            NuxeoButton {
                id: connectButton
                enabled: {
                    if (!urlInput.acceptableInput || !folderInput.text)
                        return false
                    // Browser OAuth2 flow: URL + folder are enough,
                    // credentials are entered in the browser. This
                    // also covers the case where the server disallows
                    // basic auth (the legacy checkbox is hidden and
                    // useLegacyAuth is forced off).
                    if (!control.serverAllowsBasicAuth || !useLegacyAuth.checked)
                        return true
                    // Legacy ticket auth: require username + password here.
                    return usernameInput.text.length > 0 && passwordInput.text.length > 0
                }
                text: qsTr("CONNECT") + tl.tr

                onClicked: {
                    // Ensure we've probed at least once before deciding
                    // which flow to run — protects against the user
                    // hitting Enter before onEditingFinished fires.
                    control._refreshAuthCapabilities()
                    if (control.serverAllowsBasicAuth && useLegacyAuth.checked) {
                        api.password_auth(
                            folderInput.text,
                            urlInput.text,
                            usernameInput.text,
                            passwordInput.text
                        )
                    } else {
                        // OAuth2 PKCE browser flow — opens the IdP login
                        // page in the default browser; the token is
                        // returned via the ``nxdrive://authorize`` URL
                        // scheme handler.
                        api.web_authentication(
                            urlInput.text,
                            folderInput.text,
                            false
                        )
                    }
                    control.close()
                }
            }
        }
    }

    FolderDialog {
        id: fileDialog
        currentFolder: api.default_server_local_folder()
        onAccepted: folderInput.text = api.to_local_file(fileDialog.selectedFolder)
    }
}
