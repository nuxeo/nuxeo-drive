/*
 * © 2012-2026 Hyland.
 * All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
 */

import QtQuick
import QtQuick.Layouts

RowLayout {
    id: eula
    property string linkText
    property string serverType
    property var elide: Text.ElideNone
    property string icon
    property bool fillWidth: false
    property int size: 20

    IconLabel {
        icon: eula.icon
        size: eula.size
    }

    Link {
        text: eula.linkText
        elide: eula.elide
        onClicked: api.show_eula_dialog(eula.serverType)
    }
}
