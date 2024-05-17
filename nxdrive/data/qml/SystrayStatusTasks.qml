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
                color: lightTheme
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
            Image {
                source: "../icons/tasks.svg"
            }
            //color: statusText.color
            Layout.alignment: Qt.AlignRight
            Layout.rightMargin: 30
            Layout.topMargin: -10
        }
    }
}
