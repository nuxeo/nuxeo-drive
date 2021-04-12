import QtQuick 2.15
import QtQuick.Layouts 1.15

NuxeoPopup {
    id: control
    property string message
    property string cb_text

    signal ok()
    signal cancel()

    width: 300
    height: contentHeight + buttonsArea.height + 20

    contentItem: Item {
        width: control.width; height: control.height

        ColumnLayout {
            width: parent.width - 30
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
                visible: cb_text
                text: cb_text
                checked: true
                Layout.maximumWidth: parent.width
            }

            RowLayout {
                id: buttonsArea
                Layout.alignment: Qt.AlignHCenter | Qt.AlignBottom
                spacing: 20

                // Cancel button
                NuxeoButton {
                    id: cancelButton
                    text: qsTr("CANCEL") + tl.tr
                    primary: false
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
