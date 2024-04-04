import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: taskManager
    anchors.fill: parent

    property string engineUid: "dummy"

    signal setEngine(string uid)

    onSetEngine: {
        engineUid = uid
    }

    TabBar {
        id: bar
        width: parent.width
        height: 50
        spacing: 0
        anchors.top: buttonzone.bottom
        SettingsTab {
            text: qsTr("Pending Tasks")
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
        }
    }

    Component {
        id: tasksDelegate
        Row {
            spacing: 50
            //width: parent.width
            anchors.bottomMargin: 40
            Link {
                Layout.fillWidth: true
                elide: Text.ElideMiddle
                text: qsTr("Review")
                onClicked: {
                    api.on_clicked_open_task(engineUid, task["task_id"])
                    api.close_tasks_window()
                }
            }
            ScaledText {
                text: task["task_details"]
                //padding: 5
                horizontalAlignment: Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
            }
            /*
            IconLabel {
                icon: MdiFont.Icon.folder
                iconColor: secondaryIcon
                onClicked: {
                    api.on_clicked_open_task(engineUid, task["task_id"])
                    api.close_tasks_window()
                }
            }
            */
        }
    }

    ListView {
        anchors.fill: parent
        anchors.bottomMargin: 52
        width: parent.width
        anchors.topMargin: 50
        model: tasks_model.model
        delegate: tasksDelegate
        focus: true
    }

}
