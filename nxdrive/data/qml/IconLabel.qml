import QtQuick 2.13

 ScaledText {
    id: control
    property int size: point_size * 1.6
    property string icon
    property bool enabled: true

    signal clicked()
    property string tooltip_text
    text: icon
    font {
        family: "Material Design Icons"
        pointSize: point_size * (size / point_size)
    }
    color: mediumGray

    MouseArea {
        z: parent.z + 10
        anchors.fill: parent
        anchors.margins: -3
        hoverEnabled: true
        id: mouseArea
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: control.enabled ? control.clicked() : {}
    }
    NuxeoToolTip {
        text: control.tooltip_text
        visible: control.tooltip_text && mouseArea.containsMouse
    }
}
