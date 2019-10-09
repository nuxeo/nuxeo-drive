import QtQuick 2.13
import QtQuick.Controls 2.13

ProgressBar {
    id: control
    property string color: lightBlue
    from: 0
    to: 100

    background: Rectangle {
        width: control.width
        height: control.height
        color: control.indeterminate ? "lightgoldenrodyellow" : lighterGray
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
                width: 20
                height: parent.height
            }

            XAnimator on x {
                target: cursor
                from: 0
                to: parent.width
                loops: Animation.Infinite
                duration: 15000
                // https://doc.qt.io/qt-5/qml-qtquick-animator.html
                easing.type: Easing.OutInBack
                running: control.indeterminate
            }
        }
    }
}
