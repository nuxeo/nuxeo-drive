import QtQuick 2.10

Text {
    property int size: 20
    property string icon

    text: icon
    font {
        family: "Material Design Icons"
        pixelSize: size
    }

    color: "#444"
    anchors.centerIn: parent
}