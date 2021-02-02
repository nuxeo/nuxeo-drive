import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Rectangle {
    id: conflicts
    anchors.fill: parent
    color: uiBackground

    property string engineUid: ""

    signal changed(string uid)
    signal setEngine(string uid)

    onSetEngine: engineUid = uid

    TabBar {
        id: bar
        width: parent.width; height: 50
        spacing: 0

        anchors.top: parent.top

        SettingsTab {
            text: qsTr("CONFLICTS_AND_ERRORS") + tl.tr
            barIndex: bar.currentIndex; index: 0
            anchors.top: parent.top
        }
        SettingsTab {
            text: qsTr("IGNORES_SYSTRAY").arg(IgnoredsModel.count) + tl.tr
            barIndex: bar.currentIndex; index: 1
            anchors.top: parent.top
        }
    }

    StackLayout {
        currentIndex: bar.currentIndex
        width: parent.width - 30; height: parent.height - bar.height - 20
        anchors {
            bottom: parent.bottom
            bottomMargin: 10
            horizontalCenter: parent.horizontalCenter
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: uiBackground

            ColumnLayout {
                id: content
                width: implicitWidth
                anchors.centerIn: parent
                visible: ConflictsModel.count == 0 && ErrorsModel.count == 0
                spacing: 10

                ScaledText {
                    text: qsTr("NO_CONFLICTS_TITLE") + tl.tr
                    font {
                        pointSize: point_size * 1.4
                        weight: Font.Bold
                    }
                    Layout.bottomMargin: 10
                    Layout.alignment: Qt.AlignHCenter
                }

                ScaledText {
                    text: qsTr("NO_CONFLICTS_BODY") + tl.tr
                    font.pointSize: point_size * 1.2
                    Layout.alignment: Qt.AlignHCenter
                }
            }

            Flickable {
                anchors.fill: parent
                clip: true
                contentHeight: conflictsList.height + errorsList.height + 15
                ScrollBar.vertical: ScrollBar {}

                ListView {
                    id: conflictsList
                    width: parent.width; height: contentHeight
                    spacing: 15
                    visible: ConflictsModel.count > 0
                    interactive: false

                    model: ConflictsModel
                    delegate: FileCard {
                        fileData: model
                        onResolved: conflicts.changed(engineUid)
                        onIgnored: conflicts.changed(engineUid)
                    }
                }

                ListView {
                    id: errorsList
                    width: parent.width; height: contentHeight
                    anchors {
                        top: parent.top
                        topMargin: conflictsList.height + 15
                    }
                    spacing: 15
                    visible: ErrorsModel.count > 0
                    interactive: false

                    model: ErrorsModel
                    delegate: FileCard {
                        fileData: model
                        onResolved: conflicts.changed(engineUid)
                        onIgnored: conflicts.changed(engineUid)
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: uiBackground

            ListView {
                id: ignoredsList
                anchors.fill: parent
                spacing: 15
                visible: IgnoredsModel.count > 0
                clip: true

                model: IgnoredsModel
                delegate: FileCard { fileData: model; type: "ignored" }

                ScrollBar.vertical: ScrollBar {}
            }
        }
    }
}
