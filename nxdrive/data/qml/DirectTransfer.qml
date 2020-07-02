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

    signal setEngine(string uid)

    onSetEngine: engineUid = uid

    Connections {
        target: DirectTransferModel
        onNoItems: application.close_direct_transfer_window()
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
                    // visible: DirectTransferModel.count > 0

                    model: DirectTransferModel
                    delegate: TransferItem {}
                }
            }
        }
    }
}
