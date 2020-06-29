import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import QtQuick.Window 2.13
import QtQuick.Controls.Styles 1.4
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: directTransfer
    anchors.fill: parent
    anchors.topMargin: 40
    anchors.bottomMargin: 40
    anchors.leftMargin: 20

    property string engineUid: ""
    signal setEngine(string uid)
    onSetEngine: engineUid = uid

    Connections {
        target: DirectTransferModel
        onNoItems: api.close_direct_transfer_window()
    }

    Flickable {
        id: fileList
        anchors.fill: parent

        // Grab the focus to allow scrolling using the keyboard
        focus: true

        // UP and DOWN keys to scroll
        Keys.onUpPressed: scrollBar.decrease()
        Keys.onDownPressed: scrollBar.increase()

        // The scrollbar
        ScrollBar.vertical: ScrollBar {
            id: scrollBar
        }

        contentHeight: transfers.height
        ListView {
            id: transfers
            visible: DirectTransferModel.count > 0

            width: parent.width
            height: contentHeight
            spacing: 15

            // TODO: Not yet effective
            highlight: Rectangle {
                color: lighterGray
            }

            // The test before items being transferred
            header: RowLayout {
                width: parent.width
                Rectangle {
                    Layout.fillWidth: true
                    height: 40

                    ScaledText {
                        elide: Text.ElideMiddle
                        width: parent.width
                        property var destination_link: DirectTransferModel.destination_link
                        text: qsTr("DIRECT_TRANSFER_SEND").arg(destination_link) + tl.tr
                        font.pointSize: point_size * 1.2
                        linkColor: nuxeoBlue
                        onLinkActivated: Qt.openUrlExternally(link)

                        MouseArea {
                            id: mouseArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor
                            // In order to only set a mouse cursor shape for a region without reacting to mouse
                            // events set the acceptedButtons to none. This is important to being able to click
                            // on the remote path and let Qt opening the browser at the good URL.
                            acceptedButtons: Qt.NoButton
                        }
                        NuxeoToolTip {
                            text: qsTr("OPEN_REMOTE") + tl.tr
                            visible: mouseArea.containsMouse && mouseArea.cursorShape == Qt.PointingHandCursor
                        }
                    }
                }
            }

            // Items being transferred
            model: DirectTransferModel
            delegate: TransferItem {}
        }
    }
}
