import QtQuick 2.13
import QtQuick.Layouts 1.13

RowLayout {
    id: control
    property string url
    property string icon
    property string text
    property int size: 20

    IconLabel { icon: control.icon; size: control.size }
    Link {
        text: control.text
        onClicked: manager.open_local_file(control.url)
    }
}
