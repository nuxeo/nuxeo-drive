import QtQuick 2.13

 ScaledText {
    id: control
    property int size: point_size * 1.6
    property string icon
    property bool enabled: true

    signal clicked()

    text: icon
    font {
        family: "Material Design Icons"
        pointSize: point_size * (size / point_size)
    }
    color: mediumGray

    MouseArea {
        id: mouseArea
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        anchors.fill: parent
        onClicked: control.enabled ? control.clicked() : {}
    }
}
