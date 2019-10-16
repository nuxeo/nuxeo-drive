import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13

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
            enabled: isFrozen && !LINUX
            checked: manager.get_auto_start() && !LINUX
            onClicked: {
                var success = manager.set_auto_start(checked)
                if (!success) { checked = !checked }
            }
            Layout.leftMargin: -5
        }

        NuxeoSwitch {
            text: qsTr("AUTOUPDATE") + tl.tr
            enabled: isFrozen && update_check_delay > 0
            checked: manager.get_auto_update()
            onClicked: manager.set_auto_update(checked)
            Layout.leftMargin: -5
        }

        NuxeoSwitch {
            text: qsTr("DIRECT_EDIT_AUTO_LOCK") + tl.tr
            enabled: isFrozen
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

            ScaledText { text: qsTr("LANGUAGE_SELECT") + tl.tr; color: darkGray }

            NuxeoComboBox {
                id: languageBox
                model: languageModel
                textRole: "name"

                TextMetrics { id: textMetrics; font: languageBox.font }
                Component.onCompleted: {
                    for(var i = 0; i < languageModel.rowCount(); i++){
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
        }

        ScaledText {
            text: qsTr("ADVANCED_SETTINGS") + tl.tr
            pointSize: 16
            Layout.bottomMargin: 15
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
            id: deletionPopupLink
            text: qsTr("DELETION_BEHAVIOR_CHANGE_SETTINGS") + tl.tr
            onClicked: deletionPopup.open()
        }

        Link {
            id: reportCreationLink
            text: qsTr("CREATE_REPORT") + tl.tr
            onClicked: {
                var link = api.generate_report()
                lastReportLink.text = link
            }
        }

        RowLayout {
            visible: lastReportLink.text
            ScaledText {
                text: qsTr("REPORT_GENERATED") + tl.tr
            }
            Link {
                id: lastReportLink
                onClicked: api.open_report(text)
            }
        }

        Link {
            id: addonInstallLink
            text: qsTr(enabled ? "INSTALL_ADDONS" : "ADDONS_INSTALLED") + tl.tr
            enabled: !osi.addons_installed()
            color: enabled ? nuxeoBlue : mediumGray
            visible: isFrozen && WINDOWS
            onClicked: {
                addonInstallLink.enabled = !osi.install_addons()
            }
        }
    }

    ChannelPopup { id: channelPopup }
    ProxyPopup { id: proxyPopup }
    LogLevelPopup { id: logLevelPopup }
    DeletionPopup { id: deletionPopup }
}
