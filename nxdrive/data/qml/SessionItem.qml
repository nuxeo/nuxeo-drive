import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property bool active: status == "PAUSED" || status == "ONGOING"
    property bool paused: status == "PAUSED"
    visible: !shadow
    width: parent ? parent.width : 0
    height: shadow ? 0: 116
    RowLayout {
        anchors.fill: parent
        anchors.centerIn: parent
        anchors.leftMargin: 30
        anchors.rightMargin: 30

        // The border rectangle
        Rectangle {
            border.width: 1
            border.color: grayBorder
            radius: 10

            Layout.fillWidth: true
            Layout.fillHeight: true

            GridLayout {
                columns: 2
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.bottomMargin: 8
                anchors.topMargin: 8

                // Session information column
                ColumnLayout {
                    id: session
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    // Session description
                    ScaledText {
                        text: description
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        font.pointSize: point_size * 1.2
                        color: primaryText
                    }

                    // Remote link
                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: 12

                        // Folder icon and link
                        IconLink {
                            text: remote_path
                            elide: Text.ElideMiddle
                            icon: MdiFont.Icon.folder
                            fillWidth: true
                            url: api.get_remote_document_url(engine, remote_ref)
                        }
                    }

                    // Session status
                    GridLayout {
                        columns: 4
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: active ? 4 : 0

                        IconLabel {
                            visible: status == "COMPLETED" || status == "CANCELLED"
                            icon: status == "COMPLETED" ? MdiFont.Icon.check : MdiFont.Icon.close
                            iconColor: status == "COMPLETED" ? iconSuccess : iconFailure
                        }
                        ScaledText {
                            text: progress
                            color: secondaryText
                        }
                        ScaledText {
                            text: (active ? created_on : completed_on) + tl.tr
                            color: secondaryText
                        }
                        RowLayout {
                            Layout.leftMargin: 10
                            RowLayout {
                                id: csvRow
                                visible: !active && !csvFileLink.text && uploaded > 0
                                width: csvCreationLink.width
                                IconLabel {
                                    id: csvCreationLink
                                    icon: MdiFont.Icon.csv;
                                    size: 15
                                    tooltip: qsTr("EXPORT_CSV") + tl.tr
                                    onClicked: {
                                        csvCreationLink.enabled = false
                                        try {
                                            if (api.generate_csv(uid, engine)) {
                                                csvRow.visible = false
                                                csvFileLink.visible = true
                                                csvFileLink.enabled = false
                                                csvFileLink.text = qsTr("GENERATING") + tl.tr
                                            }
                                        } finally {
                                            csvCreationLink.enabled = true
                                        }
                                    }
                                }
                            }
                            Link {
                                id: csvFileLink
                                Layout.fillWidth: true
                                elide: Text.ElideMiddle
                                visible: !active && csv_path
                                enabled: !active && csv_path != "async_gen"
                                text: active ? "" :  (csv_path == "async_gen" ? qsTr("GENERATING") : csv_path.split(/[\\/]/).pop()) + tl.tr
                                onClicked: api.open_in_explorer(csv_path)
                            }
                        }
                    }
                }

                // Pause/Resume/Cancel icons grid
                GridLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.rightMargin: 16
                    Layout.leftMargin: 40
                    columns: 2
                    visible: active

                    // Pause/Resume icon
                    IconLabel {
                        icon: paused ? MdiFont.Icon.play : MdiFont.Icon.pause
                        iconColor: primaryIcon
                        tooltip: qsTr(paused ? "RESUME" : "SUSPEND") + tl.tr
                        onClicked: {
                            enabled = false
                            try {
                                if (paused) {
                                    api.resume_session(engine, uid)
                                    cancel_button.enabled = false
                                } else {
                                    api.pause_session(engine, uid)
                                    cancel_button.enabled = true
                                }
                            } finally {
                                enabled = true
                            }
                        }
                    }

                    // Stop icon
                    IconLabel {
                        id: cancel_button
                        enabled: paused
                        icon: MdiFont.Icon.close
                        tooltip: qsTr("CANCEL") + tl.tr
                        iconColor: iconFailure
                        onClicked: {
                            enabled = false
                            enabled = !application.confirm_cancel_session(engine, uid, remote_path, total - uploaded)
                        }
                    }
                }
            }
        }
    }
}
