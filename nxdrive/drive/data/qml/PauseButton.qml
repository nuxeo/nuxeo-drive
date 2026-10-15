/*
 * © 2012-2026 Hyland.
 * All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
 */

import QtQuick
import "icon-font/Icon.js" as MdiFont

IconLabel {
    id: control
    property bool running: true
    signal toggled(bool on)
    text: running ? MdiFont.Icon.pause : MdiFont.Icon.play

    onClicked: { running = !running; control.toggled(running) }
}
