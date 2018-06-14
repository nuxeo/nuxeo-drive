import QtQuick 2.10
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    property bool running: true
    signal toggled(bool on)

    IconLabel {
        text: running ? MdiFont.Icon.pause : MdiFont.Icon.play
    }

    MouseArea {
        anchors.fill: parent
        onClicked: { running = !running; control.toggled(running) }
    }
}