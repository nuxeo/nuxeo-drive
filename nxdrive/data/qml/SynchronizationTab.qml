import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: control

    GridLayout {
        id: deletionBehavior
        columns: 2
        columnSpacing: 15

        anchors {
            left: parent.left
            top: parent.top
            leftMargin: 30
            topMargin: 30
        }
        ScaledText { text: qsTr("DELETION_BEHAVIOR_LABEL") + tl.tr; color: label }
        Link {
            id: deletionPopupLink
            text: qsTr(api.get_deletion_behavior().toUpperCase()) + tl.tr
            onClicked: deletionPopup.open()
        }
    }

    // The EngineModel list
    Rectangle {
        Layout.fillWidth: true;
        Layout.fillHeight: true
        height: parent.height
        width: parent.width
        anchors {
            top: deletionBehavior.bottom
            left: parent.left
            topMargin: 35
            leftMargin: 30
            bottomMargin: 20
        }
        Flickable {
            id: enginesList
            anchors.fill: parent
            clip: true
            contentHeight: engines.height + 100
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
                delegate: EngineSyncItem {}
            }
        }
    }

    DeletionPopup {
        id: deletionPopup
        onClosed: {
            deletionPopupLink.text = qsTr(api.get_deletion_behavior().toUpperCase()) + tl.tr
        }
    }
}
