import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

HoverRectangle {
    id: control
    property string url
    property string icon
    property string text
    property int size: 24
    width: linkIcon.width + linkText.width + 10; height: size

    Rectangle {
        id: linkIcon
        width: control.size; height: control.size
        anchors.left: parent.left

        IconLabel { icon: control.icon }
    }
    Text {
        id: linkText
        text: control.text
        anchors {
            verticalCenter: parent.verticalCenter
            left: linkIcon.right
            leftMargin: 10
        }
    }
    onClicked: manager.open_local_file(control.url)
}