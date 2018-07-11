import QtQuick 2.10

 ScaledText {
    id: control
    property int size: 20 / ratio
    property string icon

    signal clicked()

    text: icon
    font { family: "Material Design Icons"; pointSize: size }

    color: mediumGray

    MouseArea {
        id: mouseArea
        cursorShape: Qt.PointingHandCursor
        anchors.fill: parent
        onClicked: control.clicked()
    }
}
