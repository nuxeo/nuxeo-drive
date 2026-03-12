import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    // Engine UID passed from parent
    property string engineUid: ""

    // Model properties with defaults
    property bool active: status == "PAUSED" || status == "PENDING" || status == "IN_PROGRESS"
    property bool paused: status == "PAUSED"
    property bool pending: status == "PENDING"
    property bool inProgress: status == "IN_PROGRESS"

    width: parent ? parent.width : 0
    height: 116

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

                // Download information column
                ColumnLayout {
                    id: downloadInfo
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    // Title: zip_file or doc_name
                    ScaledText {
                        text: zip_file ? zip_file : doc_name
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        font.pointSize: point_size * 1.2
                        color: primaryText
                    }

                    // Download path (clickable)
                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: 12

                        // Folder icon and link to open folder
                        IconLabel {
                            icon: MdiFont.Icon.folder
                            size: 20
                        }
                        Link {
                            text: download_path || qsTr("PENDING_DOWNLOAD") + tl.tr
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                            enabled: download_path && download_path.length > 0
                            onClicked: {
                                if (download_path) {
                                    api.open_in_explorer(download_path)
                                }
                            }
                        }
                    }

                    // Download status: file_count files, folder_count folders, total_size
                    GridLayout {
                        columns: 4
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: active ? 4 : 0

                        // Status icon
                        IconLabel {
                            visible: status == "COMPLETED" || status == "CANCELLED" || status == "FAILED"
                            icon: status == "COMPLETED" ? MdiFont.Icon.check : MdiFont.Icon.close
                            iconColor: status == "COMPLETED" ? iconSuccess : iconFailure
                        }

                        // File and folder count
                        ScaledText {
                            text: {
                                var parts = [];
                                if (file_count > 0) {
                                    parts.push(file_count + " " + (file_count == 1 ? qsTr("FILE_SINGULAR") : qsTr("FILE_PLURAL")) + tl.tr);
                                }
                                if (folder_count > 0) {
                                    parts.push(folder_count + " " + (folder_count == 1 ? qsTr("FOLDER_SINGULAR") : qsTr("FOLDER_PLURAL")) + tl.tr);
                                }
                                return parts.join(", ");
                            }
                            color: secondaryText
                        }

                        // Total size
                        ScaledText {
                            text: total_size_fmt
                            color: secondaryText
                        }

                        // Created time
                        ScaledText {
                            text: created_at + tl.tr
                            color: secondaryText
                        }
                    }

                    // File names row (shown when batch has multiple files)
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        visible: batch_count > 1

                        IconLabel {
                            icon: MdiFont.Icon.fileMultiple
                            size: 16
                        }
                        ScaledText {
                            text: all_file_names || ""
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            color: secondaryText
                            font.pointSize: point_size * 0.9
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
                                    api.resume_direct_download(engine || engineUid, uid)
                                    cancel_button.enabled = false
                                } else {
                                    api.pause_direct_download(engine || engineUid, uid)
                                    cancel_button.enabled = true
                                }
                            } finally {
                                enabled = true
                            }
                        }
                    }

                    // Cancel icon
                    IconLabel {
                        id: cancel_button
                        enabled: paused
                        icon: MdiFont.Icon.close
                        tooltip: qsTr("CANCEL") + tl.tr
                        iconColor: iconFailure
                        onClicked: {
                            enabled = false
                            api.cancel_direct_download(engine || engineUid, uid)
                        }
                    }
                }
            }
        }
    }
}
