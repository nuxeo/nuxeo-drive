import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    GridLayout {
        id: accountCreation
        columns: 2
        columnSpacing: 15

        anchors {
            right: parent.right
            top: parent.top
            topMargin: 15
            rightMargin: 25
        }

        // Add a new account
        NuxeoButton {
            Layout.alignment: Qt.AlignRight
            text: qsTr("NEW_ENGINE") + tl.tr
            onClicked: newAccountPopup.open()
        }
    }

    // The EngineModel list
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        height: parent.height - accountCreation.height
        width: parent.width
        anchors {
            top: accountCreation.bottom
            left: parent.left
            topMargin: 20
            leftMargin: 30
            bottomMargin: 20
        }
        Flickable {
            id: enginesList
            anchors.fill: parent
            clip: true
            contentHeight: engines.height + accountCreation.height + 50
            width: parent.width
            ScrollBar.vertical: ScrollBar {}
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            ListView {
                id: engines
                width: parent.width;
                height: contentHeight
                spacing: 20
                interactive: false

                model: EngineModel
                delegate: EngineAccountItem {}
            }

            // Empty list
            ColumnLayout {
                id: noAccountPanel
                visible: EngineModel.count == 0

                anchors.fill: parent
                anchors.rightMargin: 60

                IconLabel {
                    icon: MdiFont.Icon.accountPlus
                    size: 128;
                    Layout.alignment: Qt.AlignHCenter
                    onClicked: newAccountPopup.open()
                }

                ScaledText {
                    text: qsTr("NO_ACCOUNT") + tl.tr
                    font{
                        pointSize: point_size * 1.2
                        weight: Font.Bold
                    }
                    Layout.alignment: Qt.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                ScaledText {
                    text: qsTr("NO_ACCOUNT_DESCR").arg(qsTr("NEW_ENGINE")) + tl.tr
                    color: mediumGray
                    Layout.maximumWidth: parent.width
                    Layout.alignment: Qt.AlignHCenter
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    NewAccountPopup { id: newAccountPopup }
}
