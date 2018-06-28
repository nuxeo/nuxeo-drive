import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Item {
    id: systray
    width: Screen.width; height: Screen.height

    signal hide()

    MouseArea {
        width: parent.width; height: parent.height
        anchors.centerIn: parent
        onClicked: systray.hide()
    }

    FontLoader {
        id: iconFont
        source: "icon-font/materialdesignicons-webfont.ttf"
    }

    signal appUpdate()
    signal pickEngine(var engine)
    signal refresh(string uid)
    signal setAutoUpdate(bool auto)
    signal setEngine(string uid)
    signal setTrayPosition(int x, int y)
    signal updateInfo(string message, string confirm, string type, string version)

    property var currentEngine

    onPickEngine: {
        currentEngine = engine
        engineText.text = engine.server
        systray.setEngine(engine.uid)
    }

    onSetTrayPosition: {
        systrayContainer.x = x
        systrayContainer.y = y
    }

    onUpdateInfo: {
        systrayInfo.text = message
        if (type == "downgrade") {
            systrayInfo.Text.color = red
        } else {
            systrayInfo.Text.color = lightBlue
        }
        systrayInfo.visible = (message != "")
    }
    
    Timer {
        id: refreshTimer
        interval: 100; running: true; repeat: false
        onTriggered: {
            itemsLeftText.count = api.get_syncing_count(currentEngine.uid)
            conflictButton.count = api.get_conflicts_count(currentEngine.uid)
            errorButton.count = api.get_errors_count(currentEngine.uid)
        }
    }

    Component.onCompleted: {
        refreshTimer.interval = 1000
        refreshTimer.repeat = true
        refreshTimer.running = true
    }

    Rectangle {
        id: systrayContainer
        width: 300; height: 370

        Rectangle {
            id: topBar
            width: systrayContainer.width - 2; height: 34
            z: 10

            anchors {
                horizontalCenter: parent.horizontalCenter
                top: parent.top
                topMargin: 1
            }

            Rectangle {
                width: engineText.width + 10; height: parent.height
                anchors.left: parent.left

                Text {
                    id: engineText

                    anchors {
                        top: parent.top
                        left: parent.left
                        leftMargin: 10
                        topMargin: 10
                    }
                    font { weight: Font.Bold; pointSize: 14 }
                    smooth: true
                }
            }

            ListView {
                id: engineTabs

                width: 125; height: parent.height
                anchors.right: settingsContainer.left

                delegate: engineTabDelegate
                model: EngineModel

                orientation: ListView.Horizontal
                layoutDirection: Qt.RightToLeft
                highlight: Rectangle {
                    color: teal
                }

                Component.onCompleted: {
                    systray.pickEngine(currentItem.engineData)
                }
                
                Component {
                    id: engineTabDelegate

                    HoverRectangle {
                        id: engine
                        property variant engineData: model
                        width: 35; height: 35

                        Rectangle { // separator
                            width: 1; height: parent.height
                            color: lightGray
                            anchors {
                                left: engineTab.left
                                leftMargin: -4
                            }
                        }

                        Image {
                            id: engineTab
                            width: 30; height: 30

                            anchors.centerIn: parent

                            source: "../icons/app_icon.svg"
                            smooth: true; fillMode: Image.PreserveAspectFit
                        }

                        onClicked: {
                            engine.ListView.view.currentIndex = index;
                            systray.pickEngine(engineData);
                        }
                    }
                }
            }

            Rectangle { // separator
                width: 1; height: parent.height
                color: lightGray
                anchors.right: settingsContainer.left
            }

            HoverRectangle {
                id: settingsContainer
                width: 40; height: parent.height
                anchors.right: parent.right

                onClicked: { contextMenu.open() }

                IconLabel { icon: MdiFont.Icon.dotsVertical }

                Menu {
                    id: contextMenu

                    MenuItem {
                        text: qsTr("SETTINGS") + tl.tr
                        font { weight: Font.Bold; pointSize: 14 }
                        onTriggered: api.show_settings("General")
                    }
                    MenuItem {
                        text: qsTr("HELP") + tl.tr
                        font { weight: Font.Bold; pointSize: 14 }
                        onTriggered: api.open_help()
                    }
                    MenuItem {
                        text: qsTr("QUIT") + tl.tr
                        font { weight: Font.Bold; pointSize: 14 }
                        onTriggered: application.quit()
                    }
                }
            }
        }

        Rectangle {
            width: systrayContainer.width - 2; height: 1
            z: 10
            color: lightGray
            anchors {
                horizontalCenter: parent.horizontalCenter
                top: topBar.bottom
            }
        }

        Rectangle {
            id: submenu
            width: systrayContainer.width - 2; height: 30
            z: 10

            anchors {
                top: topBar.bottom
                topMargin: 1
                horizontalCenter: parent.horizontalCenter
            }

            Rectangle {
                width: 203; height: parent.height

                Text {
                    anchors {
                        left: parent.left
                        top: parent.top
                        topMargin: 8
                        leftMargin: 10
                    }
                    font.pointSize: 14
                    smooth: true
                    text: qsTr("RECENTLY_UPDATED") + tl.tr
                }
            }

            Rectangle {
                width: 95; height: parent.height
                anchors.right: parent.right

                HoverRectangle {
                    id: openLocal
                    width: 30; height: parent.height

                    anchors {
                        right: parent.right
                        rightMargin: 5
                    }

                    IconLabel { icon: MdiFont.Icon.folder }

                    onClicked: api.open_local(systray.currentEngine.uid, '/')
                }

                HoverRectangle {
                    id: openRemote
                    width: 30; height: parent.height

                    anchors {
                        top: parent.top
                        right: openLocal.left
                    }

                    IconLabel { icon: MdiFont.Icon.earth }

                    onClicked: api.open_remote(systray.currentEngine.uid)
                }

                PauseButton {
                    id: suspend
                    width: 30; height: parent.height
                    onToggled: api.suspend(running)

                    anchors {
                        top: parent.top
                        right: openRemote.left
                    }
                }
            }
        }

        Rectangle {
            width: systrayContainer.width - 2; height: 1
            z: 10
            color: lightGray
            anchors {
                top: submenu.bottom
                horizontalCenter: parent.horizontalCenter
            }
        }


        ListView {
            id: recentFiles
            width: systrayContainer.width - 2; height: 250

            delegate: recentFilesDelegate
            model: FileModel
            highlight: Rectangle { color: lightGray }
            anchors {
                top: submenu.bottom
                topMargin: 1
                horizontalCenter: parent.horizontalCenter
            }

            ScrollBar.vertical: ScrollBar {}
            
            Component {
            id: recentFilesDelegate

                Rectangle {
                    id: file
                    property variant fileData: model
                    width: parent.width; height: 40

                    Text {
                        id: fileName
                        text: name

                        anchors {
                            left: parent.left
                            top: parent.top
                            topMargin: 5
                            leftMargin: 10
                        }

                        font.pointSize: 14
                    }

                    Rectangle {
                        height: 10
                        anchors {
                            top: fileName.bottom
                            left: parent.left
                            leftMargin: 10
                        }

                        Rectangle {
                            id: transferDirection
                            width: 10; height: 10
                            anchors.left: parent.left

                            IconLabel {
                                size: 10
                                icon: transfer == "upload" ? MdiFont.Icon.upload : MdiFont.Icon.download
                            }
                        }

                        Text {
                            anchors {
                                left: transferDirection.right
                                verticalCenter: parent.verticalCenter
                            }
                            color: "#999"

                            font.pointSize: 12
                            text: time
                        }
                    }

                    HoverRectangle {
                        id: local
                        width: 30; height: parent.height - 1
                        z: 20
                        onClicked: api.open_local(currentEngine.uid, path)

                        anchors {
                            right: parent.right
                            rightMargin: 5
                        }
                        
                        IconLabel {
                            size: 16
                            icon: MdiFont.Icon.folder
                        }
                    }

                    HoverRectangle {
                        id: metadata
                        width: 30; height: parent.height - 1
                        z: 20
                        onClicked: api.show_metadata(currentEngine.uid, path)

                        anchors {
                            right: local.left
                        }
                        
                        IconLabel {
                            size: 16
                            icon: MdiFont.Icon.openInNew
                        }
                    }

                    Rectangle { // separator
                        width: parent.width; height: 1
                        color: lightGray
                        anchors.bottom: parent.bottom
                    }
                }
            }
        }

        Rectangle {
            width: systrayContainer.width - 2; height: 1
            z: 10
            color: lightGray
            anchors {
                bottom: systrayBottom.top
                horizontalCenter: parent.horizontalCenter
            }
        }

        Popup {
            id: updatePopup
            y: (Screen.height - 200) / 2
            width: 300
            height: 200
            focus: true
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

            Text {
                text: updateConfirm

                anchors {
                    horizontalCenter: parent.horizontalCenter
                    top: parent.top
                    topMargin: 30
                }

                font.pointSize: 18
            }

            NuxeoCheckBox {
                id: autoUpdate

                text: qsTr("AUTOUPDATE") + tl.tr
                checked: autoUpdateValue

                anchors {
                    horizontalCenter: parent.horizontalCenter
                    bottom: parent.bottom
                    bottomMargin: 50
                }

                font.pointSize: 16
                onClicked: {
                    systray.setAutoUpdate(checked)
                }
            }

            Rectangle {
                width: 200; height: 50
                anchors {
                    bottom: parent.bottom
                    horizontalCenter: parent.horizontalCenter
                }

                NuxeoButton {
                    onClicked: { updatePopup.close() }

                    anchors {
                        left: parent.left
                        top: parent.top
                        leftMargin: 10
                        topMargin: 10
                    }
                    text: qsTr("DIRECT_EDIT_CONFLICT_CANCEL") + tl.tr
                }

                NuxeoButton {
                    inverted: true

                    onClicked: { systray.appUpdate() }

                    anchors {
                        right: parent.right
                        top: parent.top
                        leftMargin: 10
                        topMargin: 10
                    }
                    text: qsTr("UPDATE") + tl.tr
                }
            }
        }

        HoverRectangle {
            id: systrayInfo
            width: systrayContainer.width - 2; height: 30
            visible: updateMessage != ""
            opacity: 1
            color: lightGray

            property string text: updateMessage
            
            anchors {
                horizontalCenter: parent.horizontalCenter
                bottom: systrayBottom.top
            }

            Text {
                color: updateType == 'downgrade' ? red : lightBlue

                anchors.centerIn: parent

                text: systrayInfo.text

                font { weight: Font.Bold; pointSize: 12 }
            }

            onClicked: {
                updatePopup.open()
                visible = false
            }
        }

        Rectangle {
            id: systrayBottom
            width: systrayContainer.width - 2; height: 49

            anchors {
                horizontalCenter: parent.horizontalCenter
                bottom: parent.bottom
                bottomMargin: 1
            }

            Rectangle {
                id: systrayBottomRight
                width: 40; height: parent.height

                anchors {
                    top: parent.top
                    right: parent.right
                }

                IconLabel {
                    id: activity
                    property string status: "ok"

                    icon: status == "ok" ? MdiFont.Icon.check : MdiFont.Icon.sync
                }
            }

            Rectangle {
                id: systrayBottomMiddle
                width: 193; height: parent.height

                anchors {
                    top: parent.top
                    right: systrayBottomRight.left
                }

                Text {
                    id: itemsLeftText
                    property int count: 0

                    visible: count > 0
                    text: qsTr("SYNCHRONIZATION_ITEMS_LEFT").arg(count) + tl.tr

                    anchors {
                        verticalCenter: parent.verticalCenter
                        right: parent.right
                    }

                    font { weight: Font.Bold; pointSize: 14 }
                    smooth: true
                }
            }

            Rectangle {
                id: systrayBottomLeft
                width: 65; height: parent.height

                anchors {
                    top: parent.top
                    right: systrayBottomMiddle.left
                }

                NuxeoButton {
                    id: conflictButton
                    height: 15

                    property int count: 0
                    visible: count > 0
                    text: qsTr("CONFLICTS_SYSTRAY").arg(count) + tl.tr

                    darkColor: orange
                    lightColor: orange
                    inverted: true
                    font.pointSize: 10

                    onClicked: api.show_conflicts_resolution(currentEngine.uid)

                    anchors {
                        left: parent.left
                        top: parent.top
                        leftMargin: 10
                        topMargin: 8
                    }
                }

                NuxeoButton {
                    id: errorButton
                    width: parent.width; height: 15

                    property int count: 0
                    visible: count > 0
                    text: qsTr("ERRORS_SYSTRAY").arg(count) + tl.tr

                    darkColor: red
                    lightColor: red
                    inverted: true
                    font.pointSize: 10

                    onClicked: api.show_conflicts_resolution(currentEngine.uid)

                    anchors {
                        left: parent.left
                        bottom: parent.bottom
                        leftMargin: 10
                        bottomMargin: 8
                    }
                }
            }
        }
    }
}