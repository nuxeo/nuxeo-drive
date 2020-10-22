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
                        columns: 3
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.topMargin: active ? 4 : 0

                        IconLabel {
                            visible: status == "COMPLETED" || status == "CANCELLED"
                            icon: status == "COMPLETED" ? MdiFont.Icon.check : MdiFont.Icon.close
                            iconColor: status == "COMPLETED" ? "green" : "red"
                        }
                        ScaledText {
                            text: progress
                            color: darkGray
                        }
                        ScaledText {
                            text: (active ? created_on : completed_on) + tl.tr
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
