import QtQuick
import QtQuick.Layouts

RowLayout {
    id: control
    property string url
    property string icon
    property string text
    property var elide: Text.ElideNone
    property bool fillWidth: false
    property int size: 20

    IconLabel { icon: control.icon; size: control.size }
    Link {
        text: control.text
        elide: control.elide
        Layout.fillWidth: control.fillWidth
        onClicked: manager.open_local_file(control.url)
    }
}
