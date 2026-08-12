import QtQuick
import QtQuick.Controls

Popup {
    id: control
    property string title

    anchors.centerIn: Overlay.overlay
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape

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
