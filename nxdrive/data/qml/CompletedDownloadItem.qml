import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    property bool completed: status == "COMPLETED"
    property bool cancelled: status == "CANCELLED"

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
                columns: 1
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
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
                        Layout.topMargin: 8

                        // Folder icon and link to open folder
                        IconLabel {
                            icon: MdiFont.Icon.folder
                            size: 20
                        }
                        Link {
                            text: download_path || ""
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

                    // Status row: Completed/Cancelled with icon
                    GridLayout {
                        columns: 3
                        Layout.fillWidth: true
                        Layout.topMargin: 8

                        // Status icon and text
                        IconLabel {
                            icon: completed ? MdiFont.Icon.check : MdiFont.Icon.close
                            iconColor: completed ? iconSuccess : iconFailure
                        }
                        ScaledText {
                            text: completed_at + tl.tr
                            color: secondaryText
                        }

                        // File and folder count + size
                        ScaledText {
                            text: {
                                var parts = [];
                                if (file_count > 0) {
                                    parts.push(file_count + " " + (file_count == 1 ? qsTr("FILE_SINGULAR") : qsTr("FILE_PLURAL")) + tl.tr);
                                }
                                if (folder_count > 0) {
                                    parts.push(folder_count + " " + (folder_count == 1 ? qsTr("FOLDER_SINGULAR") : qsTr("FOLDER_PLURAL")) + tl.tr);
                                }
                                if (total_size_fmt) {
                                    parts.push(total_size_fmt);
                                }
                                return parts.join(", ");
                            }
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
            }
        }
    }
}
