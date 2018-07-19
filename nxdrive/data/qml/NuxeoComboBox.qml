import QtQuick 2.10
import QtQuick.Controls 2.3
import "icon-font/Icon.js" as MdiFont

ComboBox {
    id: control
    property string color: nuxeoBlue
    property int modelWidth
    width: modelWidth + 2 * contentItem.leftPadding + 2 * contentItem.rightPadding
    spacing: 10

    background: Item {
        implicitWidth: control.width
        height: contentItem.contentHeight
    }

    indicator: IconLabel {
        id: boxIcon
        icon: MdiFont.Icon.chevronDown
        color: control.color; size: 16
        anchors {
            verticalCenter: control.verticalCenter
            left: control.left
            leftMargin: contentItem.contentWidth
        }
    }

    contentItem: ScaledText {
        id: boxText
        leftPadding: 0
        rightPadding: control.indicator.width + control.spacing
        width: control.width

        text: control.displayText
        color: control.color
        verticalAlignment: Text.AlignVCenter
    }

    popup: Popup {
        y: control.height - 1
        width: control.width
        implicitHeight: contentItem.implicitHeight
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            width: control.width
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }

        background: Rectangle {
            border.color: nuxeoBlue
            radius: 2
        }
    }

    MouseArea {
        width: contentItem.contentWidth * ratio + contentItem.rightPadding + 10
        height: parent.height * 3/2
        anchors {
            verticalCenter: parent.verticalCenter
            left: parent.left
            leftMargin: -5
        }
        cursorShape: Qt.PointingHandCursor
        onClicked: control.popup.open()
    }
}
