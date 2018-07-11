import QtQuick 2.10
import QtQuick.Layouts 1.3

RowLayout {
    id: control
    property string url
    property string icon
    property string text
    property int size: 20 / ratio

    IconLabel { icon: control.icon; size: control.size }
    Link {
        text: control.text
        onClicked: manager.open_local_file(control.url)
    }
}
