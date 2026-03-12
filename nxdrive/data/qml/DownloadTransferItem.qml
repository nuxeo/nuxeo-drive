import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    width: parent ? parent.width : 0
    height: 55

    // Engine UID passed from parent
    property string engineUid: ""

    ColumnLayout {
        id: transfer
        anchors.fill: parent
        anchors.centerIn: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 3

        // Progression: transferred data
        ScaledText {
            text: qsTr("DIRECT_DOWNLOAD_DETAILS").arg(progress).arg(transferred).arg(filesize) + tl.tr
            color: secondaryText
            Layout.leftMargin: icon.width + 5
            font.pointSize: point_size * 0.8
        }

        GridLayout {
            columns: 3
            Layout.fillWidth: true
            Layout.fillHeight: true

            RowLayout {
                // Download folder icon
                IconLabel {
                    id: icon
                    icon: MdiFont.Icon.download
                    tooltip: download_path || qsTr("DOWNLOADING") + tl.tr
                    enabled: download_path && download_path.length > 0
                    onClicked: {
                        if (download_path) {
                            api.open_in_explorer(download_path)
                        }
                    }
                }

                // Progress bar
                // Note: the rect is necessary to display a nice border around the progress bar.
                Rectangle {
                    id: progressBar
                    Layout.fillWidth: true
                    height: 30
                    border.color: progressFilled
                    border.width: 1
                    radius: 3
                    opacity: 0.7

                    NuxeoProgressBar {
                        width: parent.width - 2
                        height: parent.height - 2
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: progressFilledLight
                        value: progress || 0.0
                        text: doc_name
                        indeterminate: false
                        easingType: Easing.Bezier
                    }
                }

                // Cancel icon
                IconLabel {
                    id: cancel_button
                    icon: MdiFont.Icon.close
                    tooltip: qsTr("CANCEL") + tl.tr
                    iconColor: iconFailure
                    enabled: status != "CANCELLED" && status != "COMPLETED"
                    onClicked: {
                        enabled = false
                        api.cancel_direct_download(engine || engineUid, uid)
                    }
                }
            }
        }
    }
}
