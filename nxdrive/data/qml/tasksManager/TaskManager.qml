import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.2
import QtQuick.Window 2.15
import "../icon-font/Icon.js" as MdiFont
import "../"

Rectangle {
    id: taskManager
    anchors.fill: parent

    property string engineUid: ""
    property bool showSelfTasksList: false

    signal setEngine(string uid)
    signal setSection(int index)

    onSetEngine: {
        engineUid = uid
    }
    onSetSection: {
        bar.currentIndex = index
        showSelfTasksList = false
        no_tasks_available_text.visible = false
        if (tasks_model.model.rowCount() < 1) {
            showSelfTasks()
        }
        if (tasks_model.self_model.rowCount() < 1) {
             showTasks()
        }
    }
    function showTasks() {
        showSelfTasksList = false
        bar.currentIndex = 0
        no_tasks_available_text.visible = ( (bar.currentIndex == 0 && tasks_model.model.rowCount() < 1)||(bar.currentIndex == 1 && tasks_model.self_model.rowCount() < 1) ) ? true : false
    }
    function showSelfTasks() {
        showSelfTasksList = true
        bar.currentIndex = 1
        no_tasks_available_text.visible = ( (bar.currentIndex == 0 && tasks_model.model.rowCount() < 1)||(bar.currentIndex == 1 && tasks_model.self_model.rowCount() < 1) ) ? true : false
    }

    Rectangle {
        id: refreshButton
        objectName: "refresh"

        height: 0
        width: parent.width
        color: refreshBackground
        RowLayout {
            width: parent.width
            height: parent.height
            ScaledText {
                id: refreshText
                text: qsTr("REFRESH_AVAILABLE") + tl.tr
                font.pointSize: point_size * 1.2
                leftPadding: 25
                rightPadding: 5
                topPadding: 3
            }
            NuxeoButton {
                text: qsTr("REFRESH") + tl.tr
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 30
                primary: false
                onClicked: {
                            tasks_model.loadList(api.get_Tasks_list(engineUid, false, true), api.get_username(engineUid))
                            refreshButton.height = 0
                }
            }
        }
    }

    TabBar {
        id: bar
        width: parent.width
        height: 50
        spacing: 0
        anchors.top: refreshButton.bottom
        SettingsTab {
            text: qsTr("PENDING_TASKS") + tl.tr
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
            onClicked: {
                showTasks()
            }
        }
        SettingsTab {
            text: qsTr("SELF_CREATED_TASKS") + tl.tr
            barIndex: bar.currentIndex;
            index: 1
            anchors.top: parent.top
            onClicked: {
                showSelfTasks()
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
        anchors.top: bar.bottom
        anchors.bottomMargin: 52
        width: parent.width
        anchors.topMargin: refreshButton.height == 0 ? 60 : 90
        model: tasks_model.model
        delegate: tasksDelegate
        visible: !showSelfTasksList
        topMargin: 5
        bottomMargin: 10
        leftMargin: 25
        rightMargin: 10
        spacing: 25
        clip: true
        ScrollBar.vertical: ScrollBar {
        active: true
        }
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
        anchors.topMargin: refreshButton.height == 0 ? 60 : 90
        model: tasks_model.self_model
        delegate: selftasksDelegate
        visible: showSelfTasksList
        topMargin: 5
        bottomMargin: 10
        leftMargin: 25
        rightMargin: 10
        spacing: 25
        clip: true
        ScrollBar.vertical: ScrollBar {
        active: true
        }
    }
     Text {
        id: no_tasks_available_text
        //visible: ( (bar.currentIndex == 0 && tasks_model.model.rowCount() < 1)||(bar.currentIndex == 1 && tasks_model.self_model.rowCount() < 1) ) ? true : false
        text: qsTr("NO_TASKS_AVAILABLE") + tl.tr
        font.pointSize: point_size * 1.2
        anchors.centerIn: parent
        width: parent.Width
     }
}
