import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: control

    ColumnLayout {
        width: parent.width * 0.9
        anchors {
            top: parent.top
            left: parent.left
            topMargin: 30
            leftMargin: 30
        }
        spacing: 10

        NuxeoSwitch {
            text: qsTr("AUTOSTART") + tl.tr
            enabled: isFrozen
            checked: manager.get_auto_start()
            onClicked: {
                enabled = false
                try {
                    manager.set_auto_start(checked)
                    checked = manager.get_auto_start()
                } finally {
                    enabled = true
                }
            }
            Layout.leftMargin: -5
        }

        NuxeoSwitch {
            text: qsTr("AUTOUPDATE") + tl.tr
            enabled: feat_auto_update.enabled && isFrozen && update_check_delay > 0
            checked: manager.get_auto_update()
            onClicked: manager.set_auto_update(checked)
            Layout.leftMargin: -5
        }

        NuxeoSwitch {
            text: qsTr("DIRECT_EDIT_AUTO_LOCK") + tl.tr
            enabled: feat_direct_edit.enabled && isFrozen
            checked: manager.get_direct_edit_auto_lock()
            onClicked: manager.set_direct_edit_auto_lock(checked)
            Layout.leftMargin: -5
        }

        NuxeoSwitch {
            text: qsTr("USE_LIGHT_ICONS") + tl.tr
            checked: manager.use_light_icons()
            onClicked: manager.set_light_icons(checked)
            Layout.leftMargin: -5
        }

        RowLayout {
            id: languageContainer

            Layout.topMargin: 5

            ScaledText { text: qsTr("LANGUAGE_SELECT") + tl.tr; color: primaryText }

            NuxeoComboBox {
                id: languageBox
                model: languageModel
                textRole: "name"

                TextMetrics { id: textMetrics; font: languageBox.font; }
                Component.onCompleted: {
                    // Compute the dropdown list width based on the longest item.
                    for (var i = 0; i < languageModel.rowCount(); i++) {
                        textMetrics.text = qsTr(languageModel.getName(i))
                        modelWidth = Math.max(textMetrics.width, modelWidth)
                    }
                    currentIndex = find(currentLanguage)
                }
                onActivated: {
                    tl.set_language(languageModel.getTag(languageBox.currentIndex))
                }
            }
        }

        HorizontalSeparator {
            Layout.preferredWidth: parent.width * 0.9
            Layout.topMargin: 20
            Layout.bottomMargin: 20
            color: unfocusedUnderline
        }

        ScaledText {
            text: qsTr("ADVANCED_SETTINGS") + tl.tr
            font.pointSize: point_size * 1.4
            Layout.bottomMargin: 15
            color: primaryText
        }

        Link {
            id: channelPopupLink
            text: qsTr("CHANNEL_CHANGE_SETTINGS") + tl.tr
            onClicked: channelPopup.open()
        }

        Link {
            id: proxyPopupLink
            text: qsTr("PROXY_CHANGE_SETTINGS") + tl.tr
            onClicked: proxyPopup.open()
        }

        Link {
            id: logLevelPopupLink
            text: qsTr("LOG_LEVEL_CHANGE_SETTINGS") + tl.tr
            onClicked: logLevelPopup.open()
        }
        Link {
            id: reportCreationLink
            text: qsTr("CREATE_REPORT") + tl.tr
            onClicked: {
                var link = api.generate_report()
                lastReportLink.report_url = link
                lastReportLink.text = link.split(/[\\/]/).pop()
            }
        }

        RowLayout {
            visible: lastReportLink.text
            ScaledText {
                text: qsTr("REPORT_GENERATED") + tl.tr
            }
            Link {
                id: lastReportLink
                property string report_url
                onClicked: api.open_in_explorer(report_url)
            }
        }

        Link {
            id: addonInstallLink
            text: qsTr(enabled ? "INSTALL_ADDONS" : "ADDONS_INSTALLED") + tl.tr
            enabled: !osi.addons_installed()
            color: enabled ? interactiveLink : disabledText
            visible: isFrozen && WINDOWS
            onClicked: {
                addonInstallLink.enabled = !osi.install_addons()
            }
        }
    }

    ChannelPopup { id: channelPopup }
    ProxyPopup { id: proxyPopup }
    LogLevelPopup { id: logLevelPopup }
}
