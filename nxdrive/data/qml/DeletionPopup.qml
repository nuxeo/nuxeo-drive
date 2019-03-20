import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

NuxeoPopup {
    id: control

    title: qsTr("DELETION_BEHAVIOR_CHANGE_SETTINGS") + tl.tr
    width: 400
    height: 200
    topPadding: 60
    bottomPadding: 50
    leftPadding: 50
    rightPadding: 50

    onOpened: {
        var behavior = api.get_deletion_behavior()
        switch(behavior) {
            case "unsync":
                deletionBehavior.currentIndex = 0
                break
            case "delete_server":
                deletionBehavior.currentIndex = 1
                break
        }
    }

    contentItem: GridLayout {
        columns: 2
        rowSpacing: 20
        columnSpacing: 20

        ScaledText {
            text: qsTr("DELETION_BEHAVIOR_CHANGE_SETTINGS_DESCR") + tl.tr
            wrapMode: Text.WordWrap
            Layout.columnSpan: 2
            Layout.fillWidth: true
        }

        ScaledText { text: qsTr("DELETION_BEHAVIOR") + tl.tr; color: mediumGray }
        NuxeoComboBox {
            id: deletionBehavior

            textRole: "type"
            displayText: qsTr(currentText) + tl.tr
            model: ListModel {
                ListElement { type: "UNSYNC"; value: "unsync" }
                ListElement { type: "DELETE_SERVER"; value: "delete_server" }
            }

            delegate: ItemDelegate {
                width: deletionBehavior.width
                contentItem: ScaledText {
                    text: qsTr(type) + tl.tr
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                highlighted: deletionBehavior.highlightedIndex === index
            }
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
                    var value = deletionBehavior.model.get(deletionBehavior.currentIndex).value
                    api.set_deletion_behavior(value)
                    control.close()
                }
            }
        }
    }
}
