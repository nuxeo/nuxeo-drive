import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    width: parent ? parent.width : 0
    height: 55

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 10

            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.leftMargin: 20; Layout.topMargin: 5

                // File name
                ScaledText {
                    text: name
                    color: primaryText
                    Layout.fillWidth: true
                    font.pointSize: point_size * 1.2
                    elide: Text.ElideRight
                }

                RowLayout {
                    // (Down|Up)load icon
                    IconLabel {
                        icon: last_transfer == "upload" ? MdiFont.Icon.upload : MdiFont.Icon.download
                        enabled: false
                    }
                    // Sync date
                    ScaledText {
                        text: last_sync_date
                        font.pointSize: point_size * 0.8
                        color: secondaryText
                    }
                    // File size
                    ScaledText {
                        text: size
                        font.pointSize: point_size * 0.8
                        color: secondaryText
                    }
                }
            }

            // Icon: Open the file on the server
            IconLabel {
                z: 20
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 0
                icon: MdiFont.Icon.openInApp
                iconColor: secondaryIcon
                onClicked: api.show_metadata(accountSelect.getRole("uid"), local_path)
                tooltip: qsTr("OPEN_REMOTE") + tl.tr
            }

            // Icon: Open the file locally
            IconLabel {
                z: 20
                Layout.alignment: Qt.AlignLeft
                Layout.rightMargin: 10
                icon: MdiFont.Icon.pencil
                iconColor: secondaryIcon
                onClicked: api.open_local(accountSelect.getRole("uid"), local_path)
                tooltip: qsTr("OPEN_LOCAL") + tl.tr
            }
        }
    }
}
