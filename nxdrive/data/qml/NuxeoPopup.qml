import QtQuick 2.15
import QtQuick.Controls 2.15

Popup {
    id: control
    property string title

    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    background: ShadowRectangle {
        Rectangle {
            id: titleContainer
            width: parent.width; height: 40
            anchors.top: parent.top
            radius: parent.radius
            color: uiBackground; visible: title
            ScaledText { text: title; anchors.centerIn: parent }
        }
        Rectangle {
            width: parent.width; height: 10
            anchors.bottom: titleContainer.bottom
            color: uiBackground; visible: title
        }
    }

}
