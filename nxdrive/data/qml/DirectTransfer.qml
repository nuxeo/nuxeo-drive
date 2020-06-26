import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import QtQuick.Window 2.13
import QtQuick.Controls.Styles 1.4
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: directTransfer
    anchors.fill: parent
    anchors.leftMargin: 20
    anchors.rightMargin: 20
    property string engineUid: ""

    signal setEngine(string uid)

    onSetEngine: engineUid = uid

    Connections {
        target: DirectTransferModel
        onNoItems: api.close_direct_transfer()
    }

    Flickable {
        id: fileList
        anchors.fill: parent
        width: parent.width; height: parent.height
        clip: true
        ScrollBar.vertical: ScrollBar {}
        contentHeight: transfers.height
        ListView {
            id: transfers
            width: parent.width; height: contentHeight
            spacing: 15
            visible: DirectTransferModel.count > 0
            interactive: false
            highlight: Rectangle { color: lighterGray }
            header: RowLayout {
                width: parent.width
                Rectangle {
                    width: parent.width
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.topMargin: 20
                    Layout.rightMargin: 40
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
                        }
                        NuxeoToolTip {
                            text: qsTr("OPEN_REMOTE") + tl.tr
                            visible: mouseArea.containsMouse && mouseArea.cursorShape == Qt.PointingHandCursor
                        }
                    }
                }
            }
            model: DirectTransferModel
            delegate: TransferItem {}
        }
    }
}
