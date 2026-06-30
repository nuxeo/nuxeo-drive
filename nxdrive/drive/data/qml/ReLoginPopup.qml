import QtQuick
import QtQuick.Layouts

NuxeoPopup {
    id: control
    width: 370
    height: 200
    padding: 20

    title: qsTr("RELOGIN") + tl.tr

    property string engineUid: ""
    property string username: ""

    onOpened: {
        passwordInput.text = ""
        passwordInput.focus = true
    }

    contentItem: ColumnLayout {
        spacing: 20

        ColumnLayout {
            Layout.topMargin: 30
            spacing: 15
            Keys.onReturnPressed: loginButton.clicked()
            Keys.onEnterPressed: loginButton.clicked()

            // Username (read-only)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5

                ScaledText { text: qsTr("USERNAME") + tl.tr; color: secondaryText }
                ScaledText {
                    text: control.username
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    color: mediumGray
                }
            }

            // Password
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5

                ScaledText { text: qsTr("PASSWORD") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: passwordInput
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    echoMode: TextInput.Password
                    KeyNavigation.tab: loginButton
                }
            }
        }

        // Cancel / Login buttons
        RowLayout {
            Layout.alignment: Qt.AlignRight

            NuxeoButton {
                text: qsTr("CANCEL") + tl.tr
                primary: false
                onClicked: control.close()
            }

            NuxeoButton {
                id: loginButton
                enabled: passwordInput.text.length > 0
                text: qsTr("LOGIN") + tl.tr

                onClicked: {
                    api.relogin(control.engineUid, passwordInput.text)
                    control.close()
                }
            }
        }
    }
}
