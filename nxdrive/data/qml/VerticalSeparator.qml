
import QtQuick 2.10

Rectangle {
    property real factor: 1.0
    property int size: 1
    width: size; height: parent.height * factor

    color: lightGray
}