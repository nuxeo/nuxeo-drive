import QtQuick 2.13
import QtQuick.Layouts 1.13

NuxeoPopup {
    id: control
    property string message
    property string okColor: nuxeoBlue

    signal ok()
    signal cancel()

    width: 250
    height: 150

    contentItem: Item {
        width: control.width; height: control.height

        ColumnLayout {
            width: parent.width - 30
            height: parent.height - 30
            anchors.centerIn: parent
            spacing: 20

            // The message to display
            ScaledText {
                text: message
                wrapMode: Text.WordWrap
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
            }

            // Additional checkbox (used only when removing an account)
            // It will set accountDeletion.purge_local_files when visible
            NuxeoCheckBox {
                id: confirmCheckbox
                visible: typeof(accountDeletion) !== "undefined"
                text: qsTr("PURGE_LOCAL_FILES") + tl.tr
                checked: true
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter | Qt.AlignBottom
                spacing: 20

                // Cancel button
                NuxeoButton {
                    id: cancelButton
                    text: qsTr("CANCEL") + tl.tr
                    lightColor: mediumGray
                    darkColor: darkGray
                    inverted: true
                    Layout.alignment: Qt.AlignLeft

                    onClicked: {
                        control.cancel()
                        control.close()
                    }
                }

                // OK button
                NuxeoButton {
                    id: okButton
                    text: qsTr("CONTINUE") + tl.tr
                    inverted: true
                    color: control.okColor
                    Layout.alignment: Qt.AlignRight

                    onClicked: {
                        // Update the global variable to be able to get the state in AccountsTab.qml
                        if (typeof accountDeletion !== "undefined") {
                            accountDeletion.purge_local_files = confirmCheckbox.checked
                        }

                        control.ok()
                        control.close()
                    }
                }
            }
        }
    }
}
