import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    property bool paused: status == "PAUSED" || status == "SUSPENDED"
    property bool download: transfer_type == "download"
    width: parent.width
    height: 55

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 10

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: 5

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
                        size: 12
                        icon: download ? MdiFont.Icon.download : MdiFont.Icon.upload
                        enabled: false
                    }
                    // Progression
                    ScaledText {
                        text: progress_metrics + (!download && finalizing ? " • " + qsTr("FINALIZING") + tl.tr : "")
                        font.pointSize: point_size * 0.8
                        color: mediumGray
                    }
                }
            }

            IconLabel {
                visible: !is_direct_edit && !finalizing
                z: 20; Layout.alignment: Qt.AlignRight; Layout.rightMargin: 10
                icon: paused ? MdiFont.Icon.play : MdiFont.Icon.pause
                tooltip: qsTr(paused ? "RESUME" : "SUSPEND") + tl.tr
                onClicked: {
                    // engine is set for DirectEdit transfers only
                    var engine_uid = engine || accountSelect.getRole("uid")
                    var nature = download ? "download" : "upload"
                    if (paused) {
                        api.resume_transfer(nature, engine_uid, uid)
                    } else {
                        api.pause_transfer(nature, engine_uid, uid, progress)
                    }
                }
            }
        }

        NuxeoProgressBar {
            id: progressBar
            color: finalizing ? lightGreen : lightBlue
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignRight
            Layout.leftMargin: 15
            Layout.rightMargin: 15
            height: 5
            value: progress || 0.0
            // Indeterminate progress bar when linking the blob to the document (last upload step)
            indeterminate: !download && finalizing
        }
    }
}
