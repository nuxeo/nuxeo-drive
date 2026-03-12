import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: directTransferWindow
    anchors.fill: parent

    property string engineUid: ""

    signal setEngine(string uid)

    onSetEngine: {
        engineUid = uid
        // Forward the engine to the DirectTransfer tab
        directUploadTab.setEngine(uid)
        // Update download location display
        directDownloadTab.updateDownloadLocation()
    }

    TabBar {
        id: mainTabBar
        width: parent.width
        height: 50
        spacing: 0

        SettingsTab {
            text: qsTr("DIRECT_DOWNLOAD") + tl.tr
            barIndex: mainTabBar.currentIndex
            index: 0
            anchors.top: parent.top
        }

        SettingsTab {
            text: qsTr("DIRECT_UPLOAD") + tl.tr
            barIndex: mainTabBar.currentIndex
            index: 1
            anchors.top: parent.top
        }
    }

    StackLayout {
        currentIndex: mainTabBar.currentIndex
        width: parent.width
        height: parent.height - mainTabBar.height
        anchors.top: mainTabBar.bottom

        // Tab 1: Direct Download
        DirectDownloadTab {
            id: directDownloadTab
            Layout.fillWidth: true
            Layout.fillHeight: true
            engineUid: directTransferWindow.engineUid
        }

        // Tab 2: Direct Upload (existing DirectTransfer content)
        DirectTransfer {
            id: directUploadTab
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
