import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: directDownloadTab
    anchors.fill: parent

    property string engineUid: ""
    property string downloadLocation: ""
    property int completedDownloadsCount: CompletedDirectDownloadModel.count
    property int activeDownloadsCount: ActiveDirectDownloadModel.count

    function updateDownloadLocation() {
        downloadLocation = api.get_download_location()
    }

    Component.onCompleted: {
        updateDownloadLocation()
    }

    Connections {
        target: api
        function onDownloadLocationChanged() {
            updateDownloadLocation()
        }
    }

    Connections {
        target: CompletedDirectDownloadModel

        function onDownloadChanged() {
            completedDownloadsCount = CompletedDirectDownloadModel.count
        }
    }

    Connections {
        target: ActiveDirectDownloadModel

        function onDownloadChanged() {
            activeDownloadsCount = ActiveDirectDownloadModel.count
        }
    }

    // Top button zone with download location and buttons
    Rectangle {
        id: buttonzone
        height: 90
        width: parent.width

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 10

            // First row: Download location label and buttons
            RowLayout {
                Layout.fillWidth: true

                // Download location display on the left
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 5

                    ScaledText {
                        text: qsTr("DOWNLOAD_LOCATION") + tl.tr
                        color: mediumGray
                        font.pointSize: point_size * 0.9
                    }

                    ScaledText {
                        text: downloadLocation
                        color: primaryText
                        font.pointSize: point_size * 0.9
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                        Layout.maximumWidth: 400
                    }
                }

                // Buttons on the right
                RowLayout {
                    Layout.alignment: Qt.AlignRight
                    spacing: 10

                    NuxeoButton {
                        text: qsTr("CHANGE_DOWNLOAD_LOCATION") + tl.tr
                        onClicked: api.change_download_location()
                    }
                }
            }

            // Second row: Open Folder button
            RowLayout {
                Layout.fillWidth: true

                Item {
                    Layout.fillWidth: true
                }

                NuxeoButton {
                    text: qsTr("OPEN_DOWNLOAD_FOLDER") + tl.tr
                    primary: false
                    onClicked: api.open_download_folder()
                }
            }
        }
    }

    // Sub-tabs for Running, History, Monitoring
    TabBar {
        id: subTabBar
        width: parent.width
        height: 50
        spacing: 0
        anchors.top: buttonzone.bottom

        SettingsTab {
            text: qsTr("RUNNING") + tl.tr
            barIndex: subTabBar.currentIndex
            index: 0
            anchors.top: parent.top
        }

        SettingsTab {
            text: qsTr("HISTORY") + tl.tr
            barIndex: subTabBar.currentIndex
            index: 1
            anchors.top: parent.top
            enabled: completedDownloadsCount
        }

        SettingsTab {
            text: qsTr("MONITORING") + tl.tr
            barIndex: subTabBar.currentIndex
            index: 2
            anchors.top: parent.top
            enabled: activeDownloadsCount
        }
    }

    // Content area for the sub-tabs
    StackLayout {
        currentIndex: subTabBar.currentIndex
        width: parent.width
        height: parent.height - subTabBar.height - buttonzone.height
        anchors.bottom: parent.bottom

        // Running tab content
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: activeDownloadsList
                anchors.fill: parent
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                spacing: 25

                model: ActiveDirectDownloadModel
                delegate: DirectDownloadItem {
                    engineUid: directDownloadTab.engineUid
                }

                Label {
                    anchors.fill: parent
                    horizontalAlignment: Qt.AlignHCenter
                    verticalAlignment: Qt.AlignVCenter
                    visible: ActiveDirectDownloadModel.count == 0
                    text: qsTr("NO_ACTIVE_DOWNLOADS") + tl.tr
                    font.pointSize: point_size * 1.2
                    color: primaryText
                }

                topMargin: 20
                bottomMargin: 20
                ScrollBar.vertical: ScrollBar {}
            }
        }

        // History tab content
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: completedDownloadsList
                anchors.fill: parent
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                spacing: 25

                model: CompletedDirectDownloadModel
                delegate: CompletedDownloadItem {}

                Label {
                    anchors.fill: parent
                    horizontalAlignment: Qt.AlignHCenter
                    verticalAlignment: Qt.AlignVCenter
                    visible: CompletedDirectDownloadModel.count == 0
                    text: qsTr("NO_DOWNLOAD_HISTORY") + tl.tr
                    font.pointSize: point_size * 1.2
                    color: primaryText
                }

                topMargin: 20
                bottomMargin: 20
                ScrollBar.vertical: ScrollBar {}
            }
        }

        // Monitoring tab content
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: monitoringList
                width: parent.width
                anchors.fill: parent
                anchors.topMargin: 20
                anchors.bottomMargin: 25
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                spacing: 16

                model: DirectDownloadMonitoringModel
                delegate: DownloadTransferItem {
                    engineUid: directDownloadTab.engineUid
                }

                Layout.fillWidth: true
                Layout.fillHeight: true
                ScrollBar.vertical: ScrollBar {}

                Label {
                    anchors.fill: parent
                    horizontalAlignment: Qt.AlignHCenter
                    verticalAlignment: Qt.AlignVCenter
                    visible: DirectDownloadMonitoringModel.count == 0
                    text: qsTr("NO_DOWNLOADS_TO_MONITOR") + tl.tr
                    font.pointSize: point_size * 1.2
                    color: primaryText
                }
            }

            // Information about the displayed downloads
            RowLayout {
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                anchors.margins: 5
                anchors.rightMargin: 20

                ScaledText {
                    color: lightGray
                    text: qsTr("DOWNLOAD_MONITORING_DESCRIPTION") + tl.tr
                    font.pointSize: point_size * 0.8
                }
            }
        }
    }
}
