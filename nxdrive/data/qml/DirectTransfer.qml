import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: directTransfer
    anchors.fill: parent

    property string engineUid: ""
    property int activeSessionsCount: 0
    property int completedSessionsCount: 0
    property double startTime: 0.0

    signal setEngine(string uid)

    onSetEngine: {
        engineUid = uid
        updateSessionsCounts()
    }

    function updateSessionsCounts() {
        activeSessionsCount = api.get_active_sessions_count(engineUid)
        completedSessionsCount = api.get_completed_sessions_count(engineUid)
    }

    Connections {
        target: ActiveSessionModel

        function onSessionChanged() {
            updateSessionsCounts()
        }
    }

    Connections {
        target: CompletedSessionModel

        function onSessionChanged() {
            updateSessionsCounts()
        }
    }

    // "New transfer" button
    Rectangle {
        id: buttonzone
        height: 60
        width: parent.width
        RowLayout {
            width: parent.width
            height: parent.height
            NuxeoButton {
                text: qsTr("NEW_TRANSFER") + tl.tr
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 30
                enabled: !ActiveSessionModel.is_full
                onClicked: api.open_server_folders(engineUid)
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
            text: qsTr("RUNNING") + tl.tr
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
        }

        SettingsTab {
            text: qsTr("HISTORY") + tl.tr
            barIndex: bar.currentIndex;
            index: 1
            anchors.top: parent.top
            enabled: completedSessionsCount
        }

        SettingsTab {
            text: qsTr("MONITORING") + tl.tr
            barIndex: bar.currentIndex;
            index: 2
            anchors.top: parent.top
            enabled: activeSessionsCount
        }
    }

    StackLayout {
        currentIndex: bar.currentIndex
        width: parent.width
        height: parent.height - bar.height - buttonzone.height
        anchors.bottom: parent.bottom

        // The "Active Sessions" list
        ListView {
            id: activeSessionsList
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            spacing: 25

            model: ActiveSessionModel
            delegate: SessionItem {}
            Label {
                anchors.fill: parent
                horizontalAlignment: Qt.AlignHCenter
                verticalAlignment: Qt.AlignVCenter
                visible: !ActiveSessionModel.count_no_shadow
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

        // The "Completed" sessions list
        ListView {
            id: completedSessionsList
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            spacing: 25

            model: CompletedSessionModel
            delegate: SessionItem {}
            Layout.fillWidth: true
            Layout.fillHeight: true
            topMargin: 20
            bottomMargin: 20
            ScrollBar.vertical: ScrollBar {}
        }

        // The "Monitoring" rect
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: itemsList
                width: parent.width
                anchors.fill: parent
                anchors.topMargin: 20
                anchors.bottomMargin: 25
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                spacing: 16

                model: DirectTransferModel
                delegate: TransferItem {}

                Layout.fillWidth: true
                Layout.fillHeight: true
                ScrollBar.vertical: ScrollBar {}
            }

            // Information about the filter on displayed files
            RowLayout {
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                anchors.margins: 5
                anchors.rightMargin: 20

                ScaledText {
                    color: lightGray
                    text: qsTr("MONITORING_DESCRIPTION").arg(CHUNK_SIZE) + tl.tr
                    font.pointSize: point_size * 0.8
                }
            }
        }
    }
}
