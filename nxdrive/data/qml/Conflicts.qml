import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import QtQuick.Window 2.2

Window {
    id: conflicts
    width: 550
    height: 600
    color: lighterGray

    property string engineUid

    signal changed()
    signal setEngine(string uid)

    onSetEngine: engineUid = uid

    Flickable {
        anchors.fill: parent
        contentHeight: content.height + 40

        ColumnLayout {
            id: content
            width: parent.width - 30
            anchors {
                top: parent.top
                horizontalCenter: parent.horizontalCenter
                topMargin: 20
            }

            ScaledText {
                text: qsTr("CONFLICTS_AND_ERRORS") + tl.tr
                visible: ConflictsModel.count > 0
                pointSize: 16; font.weight: Font.Bold
                Layout.bottomMargin: 10
            }

            ScaledText {
                text: qsTr("NO_CONFLICTS_TITLE") + tl.tr
                visible: ConflictsModel.count == 0
                pointSize: 16; font.weight: Font.Bold
                Layout.bottomMargin: 10
            }

            ScaledText {
                text: qsTr("NO_CONFLICTS_BODY") + tl.tr
                visible: ConflictsModel.count == 0
                pointSize: 14
            }

            ListView {
                id: conflictsList
                Layout.fillWidth: true
                height: implicitHeight
                spacing: 15
                visible: ConflictsModel.count > 0
                interactive: false

                model: ConflictsModel
                delegate: FileCard {
                    fileData: model
                    onResolved: conflicts.changed()
                    onIgnored: conflicts.changed()
                }

                ScrollBar.vertical: ScrollBar {}
            }

            ScaledText {
                text: qsTr("IGNORES_SYSTRAY").arg(IgnoredsModel.count) + tl.tr
                visible: IgnoredsModel.count > 0
                pointSize: 16; font.weight: Font.Bold
                Layout.bottomMargin: 10
            }

            ListView {
                id: ignoredsList
                Layout.fillWidth: true; height: contentHeight
                spacing: 15
                visible: IgnoredsModel.count > 0
                interactive: false

                model: IgnoredsModel
                delegate: FileCard { fileData: model; type: "ignored" }

                ScrollBar.vertical: ScrollBar {}
            }
        }
    }
}
