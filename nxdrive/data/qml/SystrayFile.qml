import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    width: parent.width; height: 55

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
                    Layout.fillWidth: true
                    font.pointSize: point_size * 1.2
                    elide: Text.ElideRight
                }

                RowLayout {
                    // (Down|Up)load icon
                    IconLabel {
                        size: 16
                        icon: last_transfer == "upload" ? MdiFont.Icon.upload : MdiFont.Icon.download
                    }
                    // Sync date
                    ScaledText {
                        text: last_sync_date
                        font.pointSize: point_size * 0.8
                        color: mediumGray
                    }
                    // File size
                    ScaledText {
                        text: size
                        font.pointSize: point_size * 0.8
                        color: mediumGray
                    }
                }
            }

            // Icon: Open the file on the server
            IconLabel {
                z: 20; Layout.alignment: Qt.AlignRight; Layout.rightMargin: 0
                icon: MdiFont.Icon.openInNew
                onClicked: api.show_metadata(accountSelect.getRole("uid"), local_path)
            }

            // Icon: Open the file locally
            IconLabel {
                z: 20; size: 24
                Layout.alignment: Qt.AlignLeft; Layout.rightMargin: 10
                icon: MdiFont.Icon.pencil
                onClicked: api.open_local(accountSelect.getRole("uid"), local_path)
            }
        }
    }
}
