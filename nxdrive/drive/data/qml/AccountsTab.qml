import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    function openNewAccountPopup() {
        api.log_qml("Add account clicked")
        if (!serverNewAccountPopupUrl) {
            api.log_qml("Add account source is empty")
            console.error("Add account popup source is empty for current server type")
            return
        }

        api.log_qml("Add account source=" + serverNewAccountPopupUrl)

        if (!newAccountPopupLoader.item || !newAccountPopupLoader.item.open) {
            api.log_qml(
                "Add account popup unavailable status="
                + newAccountPopupLoader.status
                + " source="
                + newAccountPopupLoader.source
            )
            console.error(
                "Add account popup not available. status=",
                newAccountPopupLoader.status,
                "source=",
                newAccountPopupLoader.source
            )
            return
        }

        api.log_qml("Add account popup open() requested")
        Qt.callLater(function() {
            newAccountPopupLoader.item.open()
            api.log_qml("Add account popup open() executed")
        })
    }

    GridLayout {
        id: accountCreation
        columns: 2
        columnSpacing: 15

        anchors {
            right: parent.right
            top: parent.top
            topMargin: 15
            rightMargin: 25
        }

        // Add a new account
        NuxeoButton {
            Layout.alignment: Qt.AlignRight
            text: qsTr("NEW_ENGINE") + tl.tr
            onClicked: control.openNewAccountPopup()
        }
    }

    // The EngineModel list
    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        height: parent.height - accountCreation.height
        width: parent.width
        anchors {
            top: accountCreation.bottom
            left: parent.left
            topMargin: 20
            leftMargin: 30
            bottomMargin: 20
        }
        Flickable {
            id: enginesList
            anchors.fill: parent
            clip: true
            contentHeight: engines.height + accountCreation.height + 50
            width: parent.width
            ScrollBar.vertical: ScrollBar {}
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            ListView {
                id: engines
                width: parent.width;
                height: contentHeight
                spacing: 20
                interactive: false

                model: EngineModel
                delegate: EngineAccountItem {}
            }

            // Empty list
            ColumnLayout {
                id: noAccountPanel
                visible: EngineModel.count == 0

                anchors.fill: parent
                anchors.rightMargin: 60

                IconLabel {
                    icon: MdiFont.Icon.accountPlus
                    size: 128;
                    Layout.alignment: Qt.AlignHCenter
                    onClicked: control.openNewAccountPopup()
                }

                ScaledText {
                    text: qsTr("NO_ACCOUNT") + tl.tr
                    font{
                        pointSize: point_size * 1.2
                        weight: Font.Bold
                    }
                    Layout.alignment: Qt.AlignHCenter
                    wrapMode: Text.WordWrap
                }

                ScaledText {
                    text: qsTr("NO_ACCOUNT_DESCR").arg(qsTr("NEW_ENGINE")) + tl.tr
                    color: mediumGray
                    Layout.maximumWidth: parent.width
                    Layout.alignment: Qt.AlignHCenter
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    Loader {
        id: newAccountPopupLoader
        source: serverNewAccountPopupUrl
        asynchronous: false
        active: true

        onStatusChanged: {
            if (status === Loader.Error) {
                api.log_qml("Add account loader error source=" + source)
                console.error(
                    "Add account popup failed to load. source=",
                    source
                )
            }
        }
    }

    Loader {
        id: reLoginPopupLoader
        source: serverReloginPopupUrl
        asynchronous: false
    }

    Connections {
        target: api
        function onShowReloginPopup(uid, username) {
            if (!reLoginPopupLoader.item)
                return
            reLoginPopupLoader.item.engineUid = uid
            reLoginPopupLoader.item.username = username
            reLoginPopupLoader.item.open()
        }
    }
}
