import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

HoverRectangle {
    id: control
    color: uiBackground
    Layout.fillWidth: true; height: 40
    opacity: 1

    property string icon: MdiFont.Icon.check
    property string text
    property string subText
    property string textColor: mediumGray
    property bool textVisible: true
    property bool anim: false
    property int progress: 0

    RowLayout {
        anchors.fill: parent

        Item { Layout.fillWidth: true }

        ColumnLayout {
            spacing: 0

            ScaledText {
                id: statusText
                text: control.text
                color: control.textColor
                visible: control.textVisible
                Layout.alignment: Qt.AlignRight
            }

            ScaledText {
                id: statusSubText
                text: control.subText
                visible: text
                color: statusText.color
                font.pointSize: point_size * 0.8
                opacity: 0.8
                Layout.alignment: Qt.AlignRight
            }
        }

        IconLabel {
            id: statusIcon
            icon: control.icon
            color: statusText.color
            Layout.alignment: Qt.AlignRight
            Layout.rightMargin: 10

            SequentialAnimation on rotation {
                id: syncAnim
                running: control.anim
                loops: Animation.Infinite; alwaysRunToEnd: true
                NumberAnimation { from: 360; to: 0; duration: 1000; easing.type: Easing.InOutQuad }
                PauseAnimation { duration: 250 }
            }
        }
    }

    NuxeoProgressBar {
        id: updateProgressBar
        width: control.width; height: 5
        anchors.bottom: parent.bottom
        value: control.progress
    }
}
