import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Controls.Styles 1.4
import QtQuick.Layouts 1.13
import QtQuick.Window 2.13
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property bool active: status == "PAUSED" || status == "ONGOING"
    property bool paused: status == "PAUSED"
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
            border.color: lightGray
            radius: 10

            Layout.fillWidth: true
            Layout.fillHeight: true

            GridLayout {
                columns: 2
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.bottomMargin: 8
                anchors.topMargin: 8

                // Session informations column
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
                    }

                    // Remote link
                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: 12

                        // Folder icon
                        IconLabel {
                            id: icon
                            icon: MdiFont.Icon.folder
                        }

                        Link {
                            text: remote_path
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                            onClicked: api.open_remote_document(engine, remote_ref, remote_path)
                        }
                    }

                    // Session status
                    GridLayout {
                        columns: 3
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: active ? 4 : 0

                        IconLabel {
                            visible: status == "DONE" || status == "CANCELLED"
                            icon: status == "DONE" ? MdiFont.Icon.check : MdiFont.Icon.close
                            iconColor: status == "DONE" ? "green" : "red"
                        }
                        ScaledText {
                            text: active ? qsTr("SESSION_PROGRESS").arg(uploaded + '/' + total) : qsTr("SESSION_PROGRESS").arg(uploaded)
                            color: darkGray
                        }
                        ScaledText {
                            text: active ? qsTr("STARTED_ON").arg(created_at) + tl.tr : qsTr(status + "_ON").arg(completed_at) + tl.tr
                            color: darkGray
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
                        iconColor: nuxeoBlue
                        tooltip: qsTr(paused ? "RESUME" : "SUSPEND") + tl.tr
                        onClicked: {
                            if (paused) {
                                api.resume_session(engine, uid)
                            } else {
                                api.pause_session(engine, uid)
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
                            application.confirm_cancel_session(engine, uid, remote_path, total - uploaded)
                        }
                    }
                }
            }
        }
    }
}
