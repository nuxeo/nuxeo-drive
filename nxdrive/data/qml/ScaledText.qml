import QtQuick 2.10

Text {
    property int pointSize: 12
    font.pointSize: pointSize / ratio
    elide: Text.ElideRight
}
