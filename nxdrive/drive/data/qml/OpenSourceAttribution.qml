import QtQuick
import QtQuick.Layouts

RowLayout {
    id: attribution
    property string linkText
    property string serverType
    property var elide: Text.ElideNone
    property string icon
    property bool fillWidth: false
    property int size: 20

    IconLabel {
        icon: attribution.icon
        size: attribution.size
    }

    Link {
        text: attribution.linkText
        elide: attribution.elide
        onClicked: api.show_open_source_attribution(attribution.serverType)
    }
}
