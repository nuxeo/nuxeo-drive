import QtQuick 2.15
import QtQuick.Controls 2.15

ProgressBar {
    id: control
    from: 0
    to: 100

    property string color: lightBlue
    property string bgColor: lighterGray
    property string bgColor2: "lightgoldenrodyellow"
    property string text: ""
    property int cursorSize: 20
    property int duration: 15000
    // https://doc.qt.io/qt-5/qml-qtquick-animator.html
    property int easingType: Easing.OutInBack

    background: Rectangle {
        width: control.width
        height: control.height
        color: control.indeterminate ? control.bgColor2 : control.bgColor
    }

    contentItem: Item {
        width: control.width
        height: control.height

        // Normal progress bar
        Rectangle {
            visible: !control.indeterminate
            width: control.visualPosition * parent.width
            height: parent.height
            color: control.color
        }

        // Animation for unlimited progress bar by animating alternating stripes
        Row {
            visible: control.indeterminate
            width: control.visualPosition * parent.width
            height: parent.height
            clip: true

            Rectangle {
                id: cursor
                color: control.color
                width: control.cursorSize
                height: parent.height
            }

            XAnimator on x {
                target: cursor
                from: 0
                to: parent.width - cursor.width
                loops: Animation.Infinite
                duration: control.duration
                easing.type: control.easingType
                running: control.indeterminate
            }
        }

        // Eventual text inside the progress bar
        ScaledText {
            visible: control.text
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            padding: 5
            text: control.text
            style: Text.Outline
            styleColor: lighterGray
        }
    }
}
