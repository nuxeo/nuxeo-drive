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

        property string engineUid: ""
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
            //width: parent.width
            Row {
                id: rw
                spacing: 50
                width: parent.width
                //border.color: "black"
                ScaledText {
                    text: task
                    padding: 5
                    //height: parent.height
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                }
                IconLabel {
                    icon: MdiFont.Icon.folder
                    iconColor: secondaryIcon
                    onClicked: api.on_clicked_open_task(task_id)
                }

                /*
                Link {
                    //id: csvFileLink
                    Layout.fillWidth: true
                    elide: Text.ElideMiddle
                    text: qsTr("Review")
                    //visible: task_id != ''
                    onClicked: api.on_clicked_open_task(task_id)
                }*/

                /*MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: {
                        var x = parent.x
                        var y = parent.y
                        var index = listv.indexAt(x, y)
                        listv.currentIndex = index
                    }
                }*/
            }
        }
        ListView {
            anchors.fill: parent
            anchors.bottomMargin: 52
            width: parent.width
            y: 80
            anchors.topMargin: 80
            model: tasks_model.model
            delegate: tasksDelegate
            //highlight: Rectangle{color: lightGray}
            focus: true
        }
        Button {
            id: btnShowList
            width: parent.width
            height: 30
            y: 50
            text: qsTr("show list")
            onClicked: {
                tasks_model.loadList();
            }
        }

    }
