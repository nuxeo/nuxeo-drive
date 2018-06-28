import QtQuick 2.6
import QtQuick.Controls 2.1

ComboBox {
    id: control

    background: Rectangle {
        implicitWidth: 120
        implicitHeight: 30
        border.color: control.pressed ? darkBlue : nuxeoBlue
        border.width: control.visualFocus ? 2 : 1
        radius: 2
    }
}