import QtQuick 2.15

Rectangle {
    property real factor: 1.0
    property int size: 1
    width: parent.width * factor; height: size

    color: lightGray
}
