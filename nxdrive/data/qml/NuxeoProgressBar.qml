import QtQuick 2.10
import QtQuick.Controls 2.3

ProgressBar {
    id: control
    property string color: lightBlue
    visible: value != 0
    from: 0; to: 100

    background: Rectangle {
        width: control.width
        height: control.height
        color: lighterGray
    }

    contentItem: Item {
        width: control.width
        height: control.height

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            color: control.color
        }
    }
}
