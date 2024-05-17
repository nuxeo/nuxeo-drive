import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.2
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: taskManager
    anchors.fill: parent

    property string engineUid: ""
    property bool showSelfTasksList: false

    signal setEngine(string uid)

    onSetEngine: {
        engineUid = uid
    }

    Rectangle {
        id: buttonzone
        height: 30
        width: parent.width
        RowLayout {
            width: parent.width
            height: parent.height
            NuxeoButton {
                text: qsTr("REFRESH") + tl.tr
                Layout.alignment: Qt.AlignHCenter
                Layout.rightMargin: 30
                onClicked: {
                            tasks_model.loadList(api.get_Tasks_list(engineUid), api.get_username(engineUid))
                }
            }
        }
    }

    TabBar {
        id: bar
        width: parent.width
        height: 50
        spacing: 0
        anchors.top: buttonzone.bottom
        SettingsTab {
            text: qsTr("PENDING_TASKS") + tl.tr
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
            onClicked: {
                showSelfTasksList = false
            }
        }
        SettingsTab {
            text: qsTr("SELF_CREATED_TASKS") + tl.tr
            barIndex: bar.currentIndex;
            index: 1
            anchors.top: parent.top
            onClicked: {
                showSelfTasksList = true
            }
        }
    }

    Component {
        id: tasksDelegate
        Row {
            spacing: 50
            anchors.bottomMargin: 40

            TaskListItem {
                Layout.alignment: Qt.AlignLeft
                text: task["task_details"]
                onClicked: {
                    api.on_clicked_open_task(engineUid, task["task_ids"])
                    api.close_tasks_window()
                }
            }
        }
    }

    ListView {
        anchors.fill: parent
        anchors.bottomMargin: 52
        width: parent.width
        anchors.topMargin: 90
        model: tasks_model.model
        delegate: tasksDelegate
        visible: !showSelfTasksList
        topMargin: 5
        bottomMargin: 10
        leftMargin: 25
        rightMargin: 10
        spacing: 25
        clip: true
    }

    Component {
        id: selftasksDelegate
        Row {
            spacing: 50
            anchors.bottomMargin: 40

            TaskListItem {
                Layout.alignment: Qt.AlignLeft
                text: task["self_task_details"]
                onClicked: {
                    api.on_clicked_open_task(engineUid, task["task_ids"])
                    api.close_tasks_window()
                }
            }
        }
    }

    ListView {
        anchors.fill: parent
        anchors.bottomMargin: 52
        width: parent.width
        anchors.topMargin: 90
        model: tasks_model.self_model
        delegate: selftasksDelegate
        visible: showSelfTasksList
        topMargin: 5
        bottomMargin: 10
        leftMargin: 25
        rightMargin: 10
        spacing: 25
        clip: true
    }

}
