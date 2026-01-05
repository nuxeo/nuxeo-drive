import QtQuick 2.15

 ScaledText {
    id: control
    property int size: point_size * 1.6
    property string icon
    property bool enabled: true
    property string tooltip
    property string iconColor: secondaryIcon
    property string iconColorDisabled: disabledIcon

    signal clicked()

    text: icon
    font {
        family: "Material Design Icons"
        pointSize: point_size * (size / point_size)
    }
    color: control.enabled ? control.iconColor : iconColorDisabled

    MouseArea {
        anchors.fill: parent
        hoverEnabled: control.tooltip
        id: mouseArea
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.NoCursor
        onClicked: control.enabled ? control.clicked() : {}
    }

    NuxeoToolTip {
        text: control.tooltip
        visible: control.tooltip && mouseArea.containsMouse
    }
}
