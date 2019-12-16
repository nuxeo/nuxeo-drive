import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import QtQuick.Window 2.13
import QtQuick.Controls.Styles 1.4
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    property bool paused: status == "PAUSED" || status == "SUSPENDED"
    width: parent.width
    height: 55
    ColumnLayout {
        id: transfer
        anchors.fill: parent
        anchors.centerIn: parent
        spacing: 3

        // Progression: transferred data and remote folder
        ScaledText {
            property string pretty_progress: "[" + Math.floor(progress || 0) + "%] "
            text: pretty_progress + qsTr("DIRECT_TRANSFER_DETAILS").arg(progress_metrics[0]).arg(progress_metrics[1]) + tl.tr
            Layout.leftMargin: 10
        }

        GridLayout {
            id: item_control
            property bool running: true
            columns: 2
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.rightMargin: 10
            Layout.leftMargin: 10
            // Progression: bar
            Rectangle {
                Layout.fillWidth: true
                height: 30
                border.color: nuxeoBlue
                border.width: 1
                radius: 3

                Control {
                    width: parent.width
                    height: parent.height
                    contentItem: NuxeoProgressBar {
                        id: progressBar
                        color: nuxeoBlue
                        opacity: 0.7
                        width: parent.width
                        height: parent.height
                        value: progress || 0.0
                        text: name
                        indeterminate: finalizing
                    }
                }
            }
            IconLabel {
                visible: !finalizing
                icon: paused ? MdiFont.Icon.play : MdiFont.Icon.pause
                tooltip: qsTr(paused ? "RESUME" : "SUSPEND") + tl.tr
                onClicked: {
                    if (paused) {
                        api.resume_transfer("upload", engine, uid)
                    } else {
                        api.pause_transfer("upload", engine, uid, progress)
                    }
                }
            }
        }
    }
}
