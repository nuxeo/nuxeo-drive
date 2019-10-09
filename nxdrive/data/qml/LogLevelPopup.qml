import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13

NuxeoPopup {
    id: control

    title: qsTr("LOG_LEVEL_CHANGE_SETTINGS") + tl.tr
    width: 400
    height: debugWarning.visible ? 250 : 200
    topPadding: 60
    leftPadding: 50
    rightPadding: 50
    property string level: api.get_log_level()

    onOpened: {
        var level = api.get_log_level()
        logLevel.currentIndex = logLevel.model.indexOf(level)
    }

    contentItem: GridLayout {
        columns: 2
        rowSpacing: 20
        columnSpacing: 20

        ScaledText { text: qsTr("LOG_LEVEL") + tl.tr; color: mediumGray }
        NuxeoComboBox {
            id: logLevel
            model: ["ERROR", "WARNING", "INFO", "DEBUG"]

            delegate: ItemDelegate {
                width: logLevel.width
                contentItem: ScaledText {
                    text: modelData
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                highlighted: logLevel.highlightedIndex === index
            }
        }

        ScaledText {
            id: debugWarning
            visible: logLevel.currentText == "DEBUG"
            Layout.columnSpan: 2
            Layout.maximumWidth: parent.width
            text: qsTr("LOG_LEVEL_DEBUG_WARNING") + tl.tr
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            Layout.columnSpan: 2

            NuxeoButton {
                id: cancelButton
                text: qsTr("CANCEL") + tl.tr
                lightColor: mediumGray
                darkColor: darkGray
                onClicked: control.close()
            }

            NuxeoButton {
                id: okButton
                text: qsTr("APPLY") + tl.tr
                inverted: true
                onClicked: {
                    var level = logLevel.currentText
                    api.set_log_level(level)
                    control.level = level
                    control.close()
                }
            }
        }
    }
}
