import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    width: parent.width; height: 50

    RowLayout {
        anchors.fill: parent
        spacing: 10

        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.leftMargin: 20; Layout.topMargin: 5; Layout.bottomMargin: 5

            ScaledText {
                text: name
                Layout.fillWidth: true
                font.pointSize: 14 / ratio
                elide: Text.ElideRight
            }

            RowLayout {
                IconLabel {
                    size: 16 / ratio
                    icon: last_transfer == "upload" ? MdiFont.Icon.upload : MdiFont.Icon.download
                }
                ScaledText {
                    text: last_sync_date
                    font.pointSize: 10 / ratio
                    color: mediumGray
                }
            }
        }

        IconLabel {
            z: 20; Layout.alignment: Qt.AlignRight; Layout.rightMargin: 0
            icon: MdiFont.Icon.openInNew
            onClicked: api.show_metadata(accountSelect.getRole("uid"), local_path)
        }

        IconLabel {
            z: 20; size: 24 / ratio
            Layout.alignment: Qt.AlignLeft; Layout.rightMargin: 10
            icon: MdiFont.Icon.folder
            onClicked: api.open_local(accountSelect.getRole("uid"), local_path)
        }
    }
}
