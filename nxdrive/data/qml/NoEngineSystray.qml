import QtQuick 2.0
import QtQuick.Window 2.2

Item {
    id: systray
    width: Screen.width; height: Screen.height

    signal hide()
    
    MouseArea {
        width: parent.width; height: parent.height
        anchors.centerIn: parent
        onClicked: systray.hide()
    }

    signal setTrayPosition(int x, int y)

    onSetTrayPosition: {
        systrayContainer.x = x
        systrayContainer.y = y
    }

    Rectangle {
        id: systrayContainer

        width: 300; height: 280

        property string darkBlue: "#1F28BF"
        property string lightBlue: "#0066FF"

        Image {
            id: logo
            width: 220

            anchors {
                horizontalCenter: parent.horizontalCenter
                top: parent.top
                topMargin: 30
            }
            source: "../ui5/imgs/company.png"
            smooth: true; fillMode: Image.PreserveAspectFit
        }

        Text {
            id: welcome
            width: 200

            anchors {
                horizontalCenter: parent.horizontalCenter
                top: logo.bottom
                topMargin: 45
            }
            font { weight: Font.Bold; pointSize: 16 }
            color: darkBlue
            text: qsTr("WELCOME_MESSAGE") + tl.tr
            wrapMode: Text.WordWrap
        }

        Rectangle {
            width: 200

            anchors {
                horizontalCenter: parent.horizontalCenter
                top: welcome.bottom
                topMargin: 45
            }

            NuxeoButton {
                id: quitButton
                text: qsTr("QUIT") + tl.tr

                onClicked: application.quit()

                anchors {
                    left: parent.left
                    top: parent.top
                }
            }

            NuxeoButton {
                id: accountButton
                inverted: true
                text: qsTr("SET_ACCOUNT") + tl.tr

                onClicked: api.show_settings("Accounts")

                anchors {
                    right: parent.right
                    top: parent.top
                }
            }
        }
    }
}
