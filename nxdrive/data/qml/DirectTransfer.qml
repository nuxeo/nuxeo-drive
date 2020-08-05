import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import QtQuick.Window 2.13
import QtQuick.Controls.Styles 1.4
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: directTransfer
    anchors.fill: parent

    property string engineUid: ""
    property int itemsCount: 0
    property double startTime: 0.0

    signal setEngine(string uid)
    signal setItemsCount(bool force)

    onSetEngine: engineUid = uid
    onSetItemsCount: updateCounts(force)

    function updateCounts(force) {
        // Update counts every second to go easy on the database
        var now = new Date().getTime()

        if (force || now - startTime > 1000) {
            itemsCount = api.get_dt_items_count(engineUid)
            if (itemsCount == 0) {
                application.close_direct_transfer_window()
            }
            startTime = new Date().getTime()
        }
    }

    Connections {
        target: DirectTransferModel

        function onFileChanged()  {
            updateCounts()
        }
    }

    TabBar {
        id: bar
        width: parent.width
        height: 50
        spacing: 0

        anchors.top: parent.top

        SettingsTab {
            text: qsTr("ACTIVE") + tl.tr
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
        }
        SettingsTab {
            text: qsTr("COMPLETED") + tl.tr
            barIndex: bar.currentIndex;
            index: 1
            anchors.top: parent.top
            enabled: false
        }
    }

    StackLayout {
        currentIndex: bar.currentIndex
        width: parent.width
        height: parent.height - bar.height
        anchors.bottom: parent.bottom

        // The "active" transfers rect
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Flickable {
                anchors.fill: parent
                anchors.topMargin: 20
                clip: true
                contentHeight: itemsList.height
                interactive: false

                ListView {
                    id: itemsList
                    width: parent.width
                    height: contentHeight
                    spacing: 20

                    model: DirectTransferModel
                    delegate: TransferItem {}
                }
            }

            // The number of total items to sync, including ones being synced
            RowLayout {
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                anchors.margins: 10

                // The count
                ScaledText {
                    color: lightGray
                    text: itemsCount
                }

                // The animated icon
                IconLabel {
                    color: darkGray
                    text: MdiFont.Icon.cached
                    font.pointSize: point_size * 0.8

                    SequentialAnimation on rotation {
                        running: true
                        loops: Animation.Infinite; alwaysRunToEnd: true
                        NumberAnimation { from: 360; to: 0; duration: 2000; easing.type: Easing.Linear }
                        PauseAnimation { duration: 250 }
                    }
                }
            }
        }
    }
}
