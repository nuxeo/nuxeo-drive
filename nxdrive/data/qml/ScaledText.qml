import QtQuick 2.13

Text {
    property int pointSize: 12
    font.pointSize: pointSize / ratio
    elide: Text.ElideRight
}
