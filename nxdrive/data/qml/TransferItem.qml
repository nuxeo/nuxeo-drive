import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property bool paused: status == "PAUSED" || status == "SUSPENDED"
    visible: !shadow
    width: parent ? parent.width : 0
    height: shadow ? 0: 55

    ColumnLayout {
        id: transfer
        anchors.fill: parent
        anchors.centerIn: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 3

        // Progression: transferred data
        ScaledText {
            text: qsTr("DIRECT_TRANSFER_DETAILS").arg(progress).arg(transferred).arg(filesize) + tl.tr
            color: darkGray
            Layout.leftMargin: icon.width + 5
            font.pointSize: point_size * 0.8
        }

        GridLayout {
            columns: 3
            Layout.fillWidth: true
            Layout.fillHeight: true

            RowLayout {
                // Remote folder icon
                IconLabel {
                    id: icon
                    icon: MdiFont.Icon.folder
                    tooltip: remote_parent_path
                    onClicked: api.open_remote_document(engine, remote_parent_ref, remote_parent_path)
                }

                // Progress bar
                // Note: the rect is necessary to display a nice border around the progress bar.
                Rectangle {
                    id: progressBar
                    Layout.fillWidth: true
                    height: 30
                    border.color: nuxeoBlue
                    border.width: 1
                    radius: 3
                    opacity: 0.7

                    NuxeoProgressBar {
                        width: parent.width - 2
                        height: parent.height - 2
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: nuxeoBlue50
                        bgColor2: "#eeeeee"
                        value: progress || 0.0
                        text: name
                        // Indeterminate progress bar when linking the blob to the document (last upload step)
                        indeterminate: finalizing
                        easingType: Easing.Bezier
                    }
                }

                // Pause/Resume icon
                IconLabel {
                    enabled: !finalizing
                    icon: paused ? MdiFont.Icon.play : MdiFont.Icon.pause
                    iconColor: nuxeoBlue
                    tooltip: qsTr(paused ? "RESUME" : "SUSPEND") + tl.tr
                    onClicked: {
                        if (paused) {
                            api.resume_transfer("upload", engine, uid, true)
                        } else {
                            api.pause_transfer("upload", engine, uid, progress, true)
                        }
                    }
                }

                // Stop icon
                IconLabel {
                    enabled: paused
                    icon: MdiFont.Icon.close
                    tooltip: qsTr("CANCEL") + tl.tr
                    iconColor: "red"
                    onClicked: {
                        application.confirm_cancel_transfer(engine, uid, name)
                        directTransfer.updateCounts()
                    }
                }
            }
        }
    }
}
