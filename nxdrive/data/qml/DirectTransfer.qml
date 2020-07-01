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

        // The overall rect
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // The "header" rect
            Rectangle {
                id: headerRect
                width: parent.width
                height: 60
                anchors.top: parent.top

                // The text above items
                ScaledText {
                    id: textIntro
                    anchors.fill: parent
                    anchors.margins: 20
                    elide: Text.ElideMiddle
                    text: qsTr("DIRECT_TRANSFER_SEND").arg(DirectTransferModel.destination_link) + tl.tr
                    font.pointSize: point_size * 1.2
                    linkColor: nuxeoBlue
                    onLinkActivated: Qt.openUrlExternally(link)

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: textIntro.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor
                        // In order to only set a mouse cursor shape for a region without reacting to mouse
                        // events set the acceptedButtons to none. This is important to being able to click
                        // on the remote path and let Qt opening the browser at the good URL.
                        acceptedButtons: Qt.NoButton
                    }

                    NuxeoToolTip {
                        text: qsTr("OPEN_REMOTE") + tl.tr
                        visible: textIntro.hoveredLink
                    }
                }
            }

            // The "content" rect
            Rectangle {
                width: parent.width
                height: parent.height - headerRect.height
                anchors.top: headerRect.bottom

                // The items list
                Flickable {
                    anchors.fill: parent
                    clip: true
                    contentHeight: itemsList.height + 15
                    ScrollBar.vertical: ScrollBar {}

                    ListView {
                        id: itemsList
                        width: parent.width
                        height: contentHeight
                        spacing: 20
                        visible: DirectTransferModel.count > 0
                        interactive: false

                        model: DirectTransferModel
                        delegate: TransferItem {}
                    }
                }
            }
        }
    }
}
