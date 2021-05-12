import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: control
    width: parent ? parent.width : 0
    height: 140

    RowLayout {
        anchors.fill: parent
        anchors.rightMargin: 60

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            border.width: 1
            border.color: grayBorder
            radius: 10

            GridLayout {
                columns: 2
                columnSpacing: 50
                rowSpacing: 10
                anchors.fill: parent
                anchors.margins: 14

                // Server URL and Username
                ScaledText { text: remote_user; color: label; font.bold: true }
                Link {
                    text: server_url
                    onClicked: api.open_remote_server(uid)
                }

                // Local folder
                ScaledText {
                    text: qsTr("ENGINE_FOLDER") + tl.tr
                    color: label
                }
                Link {
                    text: folder
                    onClicked: api.open_local(uid, "/")
                }

                // Disk space details
                ScaledText {
                    text: qsTr("STORAGE") + tl.tr;
                    color: label
                }
                Rectangle {
                    height: 20
                    width: 350
                    border.color: progressFilled
                    border.width: 1
                    radius: 2
                    Row {
                        anchors.fill: parent
                        anchors.margins: 2

                        property var disk_info: api.get_disk_space_info_to_width(uid, folder, width)

                        RectangleTooltip {
                            color: interactiveLink;
                            width: parent.disk_info[2]
                            height: parent.height
                            tooltip: "%1\n%2".arg(APP_NAME).arg(api.get_drive_disk_space(uid))
                        }

                        RectangleTooltip {
                            color: disabledText;
                            width: parent.disk_info[1]
                            height: parent.height
                            tooltip: qsTr("OTHER") + "\n%1".arg(api.get_used_space_without_synced(uid, folder)) + tl.tr
                        }

                        RectangleTooltip {
                            width: parent.disk_info[0]
                            height: parent.height
                            tooltip: qsTr("AVAILABLE") + "\n%1".arg(api.get_free_disk_space(folder)) + tl.tr
                        }
                    }
                }

                // Filters
                ScaledText {
                    text: qsTr("SELECTIVE_SYNC") + tl.tr
                    color: label
                    Layout.alignment: Qt.AlignTop
                }
                Link {
                    text: qsTr("SELECT_SYNC_FOLDERS") + tl.tr
                    onClicked: api.filters_dialog(uid)
                }
            }
        }
    }
}
