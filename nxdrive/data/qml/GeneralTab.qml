import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control


    FontLoader {
        id: iconFont
        source: "icon-font/materialdesignicons-webfont.ttf"
    }

    Rectangle {
        width: parent.width - 100; height: parent.height - 100
        anchors.centerIn: parent

        NuxeoSwitch {
            id: autoStart
            text: qsTr("AUTOSTART") + tl.tr
            checked: manager.get_auto_start()
            onClicked: manager.set_auto_start(checked)
            anchors {
                top: parent.top
                left: parent.left
            }
        }

        NuxeoSwitch {
            id: autoUpdate
            text: qsTr("AUTOUPDATE") + tl.tr
            checked: manager.get_auto_update()
            onClicked: manager.set_auto_update(checked)
            anchors {
                top: autoStart.bottom
                left: parent.left
            }
        }

        NuxeoSwitch {
            id: autoLock
            text: qsTr("DIRECT_EDIT_AUTO_LOCK") + tl.tr
            checked: manager.get_direct_edit_auto_lock()
            onClicked: manager.set_direct_edit_auto_lock(checked)
            anchors {
                top: autoUpdate.bottom
                left: parent.left
            }
        }

        NuxeoSwitch {
            id: betaChannel
            text: qsTr("BETACHANNEL") + tl.tr
            checked: manager.get_beta_channel()
            onClicked: manager.set_beta_channel(checked)
            anchors {
                top: autoLock.bottom
                left: parent.left
            }
        }

        NuxeoSwitch {
            id: tracker
            text: qsTr("TRACKER") + tl.tr
            checked: manager.get_tracking()
            onClicked: manager.set_tracking(checked)
            anchors {
                top: betaChannel.bottom
                left: parent.left
            }
        }

        Rectangle {
            id: languageContainer
            width: parent.width; height: 50
            anchors {
                top: tracker.bottom
                left: parent.left
                topMargin: 10
            }

            Text {
                id: languageBoxLabel
                text: qsTr("LANGUAGE_SELECT") + tl.tr
                anchors {
                    verticalCenter: parent.verticalCenter
                    left: parent.left
                }
            }
            NuxeoComboBox {
                id: languageBox
                model: languageModel
                textRole: "name"
                
                delegate: ItemDelegate {
                    text: name
                    property string abbr: tag
                    width: parent.width
                }

                Component.onCompleted: currentIndex = find(currentLanguage)

                onActivated: {
                    var lang = languageBox.model.getTag(languageBox.currentIndex)
                    tl._set(lang)
                }

                anchors {
                    verticalCenter: parent.verticalCenter
                    left: languageBoxLabel.right
                    leftMargin: 10
                }
            }
        }

        NuxeoButton {
            id: proxyButton
            text: "Change proxy settings"
            size: 14
            anchors {
                left: languageContainer.left
                top: languageContainer.bottom
                topMargin: 20
            }
            onClicked: proxyPopup.open()
        }

        NuxeoButton {
            id: reportButton
            text: qsTr("CREATE_REPORT") + tl.tr
            size: 14
            anchors {
                left: proxyButton.left
                top: proxyButton.bottom
                topMargin: 20
            }
            onClicked: {
                var link = api.generate_report()
                reportLink.text = link
            } 
        }

        Item {
            width: parent.width; height: 30
            anchors {
                top: reportButton.bottom
                topMargin: 20
            }
            visible: reportLink.text
            Text {
                id: reportLabel
                text: qsTr("REPORT_GENERATED") + tl.tr
                font.pointSize: 14
                anchors.verticalCenter: parent.verticalCenter
            }
            Link {
                id: reportLink
                size: 12
                anchors {
                    verticalCenter: parent.verticalCenter
                    left: reportLabel.right
                    leftMargin: 10
                }
                onClicked: api.open_report(text)
            }
        }
    }

    ProxyPopup { id: proxyPopup }
}