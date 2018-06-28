import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Popup {
    id: control
    property string message

    signal ok()
    signal cancel()

    width: 300
    height: 200
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    
    background: ShadowRectangle { border.width: 0 }

    Text {
        text: message
        anchors {
            horizontalCenter: parent.horizontalCenter
            top: parent.top
            topMargin: 20
        }
    }

    NuxeoButton {
        id: cancelButton
        text: qsTr("ROOT_USED_CANCEL")
        lightColor: mediumGray
        darkColor: "#333"
        inverted: true
        size: 14
        anchors {
            left: parent.left
            bottom: parent.bottom
            leftMargin: 30
            bottomMargin: 30
        }
        onClicked: { control.cancel(); control.close() }
    }

    NuxeoButton {
        id: okButton
        text: qsTr("ROOT_USED_CONTINUE")
        inverted: true
        size: 14
        anchors {
            right: parent.right
            bottom: parent.bottom
            rightMargin: 30
            bottomMargin: 30
        }
        onClicked: { control.ok(); control.close() }
    }
}