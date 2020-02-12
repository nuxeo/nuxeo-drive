import QtQuick 2.13

 ScaledText {
    id: control
    property int size: point_size * 1.6
    property string icon
    property bool enabled: true
    property string tooltip

    signal clicked()

    text: icon
    font {
        family: "Material Design Icons"
        pointSize: point_size * (size / point_size)
    }
    color: mediumGray

    MouseArea {
        anchors.fill: parent
        hoverEnabled: control.tooltip
        id: mouseArea
        cursorShape: control.enabled || control.tooltip ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: control.enabled ? control.clicked() : {}
    }

    NuxeoToolTip {
        text: control.tooltip
        visible: control.tooltip && mouseArea.containsMouse
    }
}
