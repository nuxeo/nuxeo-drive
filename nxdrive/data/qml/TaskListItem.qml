import QtQuick 2.15
import QtQuick.Controls 2.15

Button {
    id: control
    width: 500
    height: 100

    contentItem: Rectangle{
        ScaledText {
            id: buttonText1
            text: api.get_text(control.text, "wf_name")
            font.pointSize: point_size * 1.2

            leftPadding: 25
            rightPadding: 5
            topPadding: 10
            anchors {
                centerIn: buttonBackground
            }
        }
        ScaledText {
            id: buttonText2
            text: api.get_text(control.text, "name")
            font.pointSize: point_size * 1.1
            color: buttonGrayText
            leftPadding: 25
            rightPadding: 5
            topPadding: 30
            anchors {
                centerIn: buttonBackground
            }
        }
        ScaledText {
            id: buttonText3
            text: api.get_text(control.text, "due")

            leftPadding: 25
            rightPadding: 5
            topPadding: 50
            anchors {
                centerIn: buttonBackground
            }
            color: api.text_red(control.text) ? buttonRedText : buttonGreenText
        }
        ScaledText {
            id: buttonText4
            text: api.get_text(control.text, "model")

            leftPadding: 25
            rightPadding: 5
            topPadding: 65
            anchors {
                centerIn: buttonBackground
            }
            //color: api.text_red(control.text) ? buttonRedText : buttongreenText
        }
    }

    background: Rectangle {
        id: buttonBackground
        width: 500
        height: buttonText1.text ? 95 : 0
        radius: 10

        border {
            width: 1
            color: grayBorder
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        width: 500
        onPressed: mouse.accepted = false
    }
}
