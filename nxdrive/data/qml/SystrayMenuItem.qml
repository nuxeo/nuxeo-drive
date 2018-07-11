import QtQuick 2.10
import QtQuick.Controls 2.3

MenuItem {
    id: control

    background: Rectangle {
        implicitWidth: 100
        implicitHeight: 20
        color: highlighted ? lightGray : lighterGray
    }
}
