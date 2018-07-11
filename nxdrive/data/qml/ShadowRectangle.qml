import QtQuick 2.10
import QtGraphicalEffects 1.0

Rectangle {
    id: control
    radius: 8

    property string shadowColor: "#40000000"
    property int hOffset: 0
    property int vOffset: 10
    property int samples: 200

    layer.enabled: true
    layer.effect: DropShadow {
        cached: true
        horizontalOffset: control.hOffset
        verticalOffset: control.vOffset
        samples: control.samples
        color: control.shadowColor
    }
}
