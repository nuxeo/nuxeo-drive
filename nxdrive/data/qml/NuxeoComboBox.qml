import QtQuick 2.10
import QtQuick.Controls 2.3
import "icon-font/Icon.js" as MdiFont

ComboBox {
    id: control
    property string color: nuxeoBlue
    spacing: 10

    font.pointSize: 12 / ratio

    background: Item {
        width: contentItem.contentWidth + 25
        height: contentItem.contentHeight
    }

    indicator: Item {
        width: 16
        height: contentItem.contentHeight
        anchors.right: background.right
        anchors.top: background.top
        IconLabel {
            id: boxIcon
            icon: MdiFont.Icon.chevronDown
            color: control.color; size: 16
            anchors.centerIn: parent
        }
    }

    contentItem: ScaledText {
        id: boxText
        leftPadding: 0
        rightPadding: control.indicator.width + control.spacing

        text: control.displayText
        font: control.font
        color: control.color
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight

        MouseArea {
            width: parent.width * 3/2
            height: parent.height * 3/2
            anchors.centerIn: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: control.popup.open()
        }
    }

    popup: Popup {
        y: control.height - 1
        width: control.width
        implicitHeight: contentItem.implicitHeight
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }

        background: Rectangle {
            border.color: nuxeoBlue
            radius: 2
        }
    }
}
