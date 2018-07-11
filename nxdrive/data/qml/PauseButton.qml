import QtQuick 2.10
import "icon-font/Icon.js" as MdiFont

IconLabel {
    id: control
    property bool running: true
    signal toggled(bool on)
    text: running ? MdiFont.Icon.pause : MdiFont.Icon.play

    onClicked: { running = !running; control.toggled(running) }
}
