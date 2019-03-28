import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    visible: progress > 0 && progress < 100
    width: parent.width; height: visible ? 55 : 0

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.leftMargin: 20; Layout.rightMargin: 20
            Layout.topMargin: 5

            ScaledText {
                text: name
                Layout.fillWidth: true
                pointSize: 14
                elide: Text.ElideRight
            }

            RowLayout {
                IconLabel {
                    size: 16
                    icon: last_transfer == "Upload" ? MdiFont.Icon.upload : MdiFont.Icon.download
                }
            }
        }

        NuxeoProgressBar {
            id: progressBar
            Layout.fillWidth: true; Layout.alignment: Qt.AlignRight
            Layout.leftMargin: 15; Layout.rightMargin: 15
            height: 5
            value: progress
        }
    }
}
