import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

/*
Rectangle {
    id: taskManager
    anchors.fill: parent

    property string engineUid: ""
    //property list pendingDocumentsList: []
    property bool pendingDocumentsPresent: true

    signal setEngine(string uid)

    onSetEngine: {
        engineUid = uid
        updateList()
        pendingDocumentsPresent = true
    }

    function updateList() {
        // pendingDocumentsList = api.get_Tasks_list()
        pendingDocumentsPresent = api.get_Tasks_count()
        //pendingDocumentsPresent = True
    }

    Connections {
        target: TasksModel
    }

    TabBar {
        id: bar
        width: parent.width
        height: 50
        spacing: 0

        anchors.top: buttonzone.bottom

        SettingsTab {
            text: qsTr("Tasks") + tl.tr
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
        }

   }

   Text {
            anchors.fill: parent
            horizontalAlignment: Qt.AlignHCenter
            verticalAlignment: Qt.AlignVCenter
            height: 100
            //textFormat: Text.RichText
            text: "No Tasks Available"
            visible: !pendingDocumentsPresent
            font.pointSize: point_size * 1.2
            color: primaryText
        }


    StackLayout {
        currentIndex: bar.currentIndex
        width: parent.width
        height: parent.height - bar.height - buttonzone.height
        anchors.bottom: parent.bottom

        // The "Pending Tasks" list
        ListView {
            id: activeTasksList
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            spacing: 25

            model: TasksModel
            delegate: SessionItem {}
            Label {
                anchors.fill: parent
                horizontalAlignment: Qt.AlignHCenter
                verticalAlignment: Qt.AlignVCenter
                // visible: !ActiveSessionModel.count_no_shadow
                visible: true
                text: qsTr("NO_ACTIVE_SESSION") + tl.tr
                font.pointSize: point_size * 1.2
                color: primaryText
            }

            Layout.fillWidth: true
            Layout.fillHeight: true
            topMargin: 20
            bottomMargin: 20
            ScrollBar.vertical: ScrollBar {}
        }
    }
}
*/

Rectangle {
        id: taskManager
        anchors.fill: parent

        Component {
            id: tasksDelegate
            Row {
                spacing: 50
                Text {
                    text: task
                }
            }
        }

        ListView {
            anchors.fill: parent
            anchors.bottomMargin: 52
            model: tasks_model.model
            /*
            model: ListModel {
                ListElement {
                    task: "Task 1"
                }
                ListElement {
                    task: "Task 2"
                }
                ListElement {
                    task: "Task 3"
                }
            }
            */
            delegate: tasksDelegate
        }

        Button {
            id: btnShowList

            x: 200
            y: 200
            text: qsTr("show list")
            onClicked: {
                tasks_model.loadList();
            }
        }
    }
