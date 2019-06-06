import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property variant fileData: model
    property bool paused: status == "PAUSED" || status == "SUSPENDED"
    property bool download: transfer_type == "download"
    visible: progress > 0 && progress < 100 || true
    width: parent.width; height: visible ? 55 : 0

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 10

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
                        icon: download ? MdiFont.Icon.download : MdiFont.Icon.upload
                    }
                }
            }

            IconLabel {
                visible: !is_direct_edit
                z: 20; Layout.alignment: Qt.AlignRight; Layout.rightMargin: 10
                icon: paused ? MdiFont.Icon.play : MdiFont.Icon.pause
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
            color: verifying ? lightGreen : lightBlue
            Layout.fillWidth: true; Layout.alignment: Qt.AlignRight
            Layout.leftMargin: 15; Layout.rightMargin: 15
            height: 5
            value: progress || 0.0
        }
    }
}
