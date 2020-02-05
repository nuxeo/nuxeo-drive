import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import QtQuick.Window 2.13
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: systray
    width: 300; height: 370
    border {
        width: 1
        color: "#33000000"
    }

    property bool hasAccounts: EngineModel.count > 0
    property double startTime: 0.0

    signal appUpdate(string version)
    signal getLastFiles(string uid)
    signal setStatus(string sync, string error, string update)
    signal updateAvailable()
    signal updateProgress(int progress)

    function doUpdateCounts() {
        systrayContainer.syncingCount = api.get_syncing_count(accountSelect.getRole("uid"))
        systrayContainer.extraCount = api.get_last_files_count(accountSelect.getRole("uid")) - 10
    }

    function updateCounts(force) {
        // Update counts every 2 seconds to go easy on the database
        var now = new Date().getTime()

        if (now - startTime > 2000) {
            doUpdateCounts()
            startTime = new Date().getTime()
        }
    }

    Connections {
        target: EngineModel
        onEngineChanged: accountSelect.currentIndex = EngineModel.count - 1
    }

    Connections {
        target: TransferModel
        onFileChanged: doUpdateCounts()
    }

    Connections {
        target: FileModel
        onFileChanged: doUpdateCounts()
    }

    Connections {
        target: systrayWindow
        onVisibleChanged: {
            contextMenu.visible = false
            fileList.contentY = 0
        }
    }

    onSetStatus:  {
        syncState.state = sync
        errorState.state = error
        updateState.state = update

        // Force the counts update at the end of the sync
        if (sync == "") {
            doUpdateCounts()
        }
    }

    onUpdateAvailable: updateState.state = api.get_update_status()
    onUpdateProgress: {
        updateState.state = api.get_update_status()
        updateState.progress = progress
    }

    FontLoader {
        id: iconFont
        source: "icon-font/materialdesignicons-webfont.ttf"
    }

    ColumnLayout {
        id: systrayContainer
        visible: hasAccounts
        width: parent.width - 2
        height: parent.height - 2
        property int syncingCount: 0
        property int extraCount: 0

        anchors.centerIn: parent
        z: 5; spacing: 0

        Rectangle {
            Layout.fillWidth: true
            color: lighterGray
            height: 50; z: 10

            MouseArea {
                width: systray.width; height: systray.height
                propagateComposedEvents: true
                visible: contextMenu.visible

                anchors {
                    top: parent.top
                    left: parent.left
                }
                onClicked: contextMenu.visible = false
            }

            RowLayout {
                anchors.fill: parent

                // Icon 1: accounts
                IconLabel {
                    id: accountIcon
                    icon: MdiFont.Icon.accountOutline
                }

                // Accounts list
                ColumnLayout {
                    Layout.maximumWidth: parent.width / 2

                    AccountsComboBox {
                        id: accountSelect

                        // Width management: systray width minus the 5 icon's width
                        Layout.preferredWidth: systray.width - (accountIcon.width * 5)

                        // When picking an account, refresh the file list.
                        onActivated: {
                            getLastFiles(accountSelect.getRole("uid"))
                            doUpdateCounts()
                        }
                    }

                    // The current account server URL
                    ScaledText {
                        id: accountUrl
                        Layout.maximumWidth: parent.width
                        text: accountSelect.getRole("server_url")
                        font.pointSize: point_size * 0.8
                        color: mediumGray

                        MouseArea {
                            id: urlHover
                            z: parent.z + 10
                            anchors.fill: parent
                            anchors.margins: -3
                            hoverEnabled: true
                        }
                        NuxeoToolTip {
                            text: accountUrl.text
                            visible: urlHover.containsMouse
                        }
                    }
                }

                // Icon 2: open remote server's URL
                IconLabel {
                    icon: MdiFont.Icon.openInNew
                    MouseArea {
                            id: nuxeoIconHover
                            z: parent.z + 10
                            anchors.fill: parent
                            anchors.margins: -3
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: api.open_remote_server(accountSelect.getRole("uid"))
                        }
                        NuxeoToolTip {
                            text: "Browse nuxeo server"
                            visible: nuxeoIconHover.containsMouse
                        }
                }

                // Icon 3: open local sync root folder
                IconLabel {
                    icon: MdiFont.Icon.folder
                    MouseArea {
                            id: folderIconHover
                            z: parent.z + 10
                            anchors.fill: parent
                            anchors.margins: -3
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: api.open_local(accountSelect.getRole("uid"), "/")
                        }
                        NuxeoToolTip {
                            text: "Open nuxeo drive folder"
                            visible: folderIconHover.containsMouse
                        }
                }

                // Icon 4: open the Direct Transfer window
                IconLabel {
                    icon: MdiFont.Icon.cloudUpload
                    MouseArea {
                            id: directTransferIconHover
                            z: parent.z + 10
                            anchors.fill: parent
                            anchors.margins: -3
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: api.open_direct_transfer(accountSelect.getRole("uid"))
                        }
                        NuxeoToolTip {
                            text: "Upload file to server"
                            visible: directTransferIconHover.containsMouse
                        }
                }

                // Icon 5: sub-menu
                IconLabel {
                    id: settingsContainer
                    icon: MdiFont.Icon.dotsVertical
                    onClicked: contextMenu.visible = !contextMenu.visible
                }
            }

            // The sub-menu
            SystrayMenu {
                id: contextMenu
                anchors {
                    right: parent.right
                    top: parent.bottom
                }
            }
        }

        // Transferring/synced files list
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true

            Flickable {
                id: fileList
                anchors.fill: parent
                clip: true
                contentHeight: actions.height + recentFiles.height + 15
                ScrollBar.vertical: ScrollBar {}

                ListView {
                    id: actions
                    width: parent.width; height: contentHeight
                    spacing: 15
                    visible: TransferModel.count > 0
                    interactive: false
                    highlight: Rectangle { color: lighterGray }

                    model: TransferModel
                    delegate: SystrayTransfer {}
                }

                ListView {
                    id: recentFiles
                    width: parent.width; height: contentHeight
                    anchors {
                        top: parent.top
                        topMargin: actions.height
                    }
                    spacing: 15
                    visible: FileModel.count > 0
                    interactive: false
                    highlight: Rectangle { color: lighterGray }

                    model: FileModel
                    delegate: SystrayFile {}
                    footer: Rectangle {
                        id: recentFooter
                        width: parent.width
                        height: systrayContainer.extraCount > 0 ? 30 : 0
                        visible: systrayContainer.extraCount > 0
                        Text {
                            text: qsTr("EXTRA_FILE_COUNT").arg(systrayContainer.extraCount) + tl.tr
                            anchors.centerIn: parent
                            color: mediumGray
                        }
                    }
                }
            }
        }

        // Sync status (items remaining to sync, or small text when sync is over)
        SystrayStatus {
            id: syncState
            state: ""  // Synced
            visible: !(errorState.visible || updateState.visible)
            text: sync_enabled ? qsTr("SYNCHRONIZATION_COMPLETED") + tl.tr : ""

            states: [
                State {
                    name: "restart"
                    PropertyChanges {
                        target: syncState
                        icon: MdiFont.Icon.pause
                        text: qsTr("RESTART_NEEDED") + tl.tr
                    }
                },
                State {
                    name: "suspended"
                    PropertyChanges {
                        target: syncState
                        icon: MdiFont.Icon.pause
                        text: qsTr("ENGINE_PAUSED") + tl.tr
                    }
                },
                State {
                    name: "syncing"
                    PropertyChanges {
                        target: syncState
                        icon: MdiFont.Icon.sync
                        text: qsTr("SYNCHRONIZATION_ITEMS_LEFT").arg(systrayContainer.syncingCount) + tl.tr
                        textVisible: systrayContainer.syncingCount > 0
                        anim: true
                    }
                }
            ]
        }

        // Error status
        SystrayStatus {
            id: errorState
            state: ""  // no errors/conflicts
            visible: state != "" && (state == "auth_expired" || (ConflictsModel.count + ErrorsModel.count) > 0)
            textColor: "white"
            icon: MdiFont.Icon.alert

            states: [
                State {
                    name: "conflicted"
                    PropertyChanges {
                        target: errorState
                        color: orange
                        text: qsTr("CONFLICTS_SYSTRAY").arg(ConflictsModel.count) + tl.tr
                        onClicked: api.show_conflicts_resolution(accountSelect.getRole("uid"))
                    }
                },
                State {
                    name: "auth_expired"
                    PropertyChanges {
                        target: errorState
                        color: red
                        text: qsTr("AUTH_EXPIRED") + tl.tr
                        subText: qsTr("AUTH_UPDATE_ACTION") + tl.tr
                        onClicked: api.web_update_token(accountSelect.getRole("uid"))
                    }
                },
                State {
                    name: "error"
                    PropertyChanges {
                        target: errorState
                        color: red
                        text: qsTr("ERRORS_SYSTRAY").arg(ErrorsModel.count) + tl.tr
                        onClicked: api.show_conflicts_resolution(accountSelect.getRole("uid"))
                    }
                }
            ]
        }

        // Update status
        SystrayStatus {
            id: updateState
            state: "up_to_date"
            visible: !(state == "up_to_date" || state == "unavailable_site" || state == "wrong_channel")
            color: lightBlue
            textColor: "white"
            icon: MdiFont.Icon.update

            states: [
                State {
                    name: "update_available"
                    PropertyChanges {
                        target: updatePopup
                        version: api.get_update_version()
                        channel: api.get_update_channel()
                    }
                    PropertyChanges {
                        target: updateState
                        text: qsTr("NOTIF_UPDATE_TITLE") + tl.tr
                        onClicked: updatePopup.open()
                    }
                },
                State {
                    name: "updating"
                    PropertyChanges {
                        target: updateState
                        text: qsTr("UPDATING_VERSION").arg(api.get_update_version()) + tl.tr
                    }
                },
                State {
                    name: "incompatible_server"
                    PropertyChanges {
                        target: updatePopup
                        version: api.get_update_version()
                        channel: api.get_update_channel()
                    }
                    PropertyChanges {
                        target: updateState
                        color: red
                        text: qsTr("NOTIF_UPDATE_DOWNGRADE").arg(api.get_update_version()) + tl.tr
                        onClicked: updatePopup.open()
                    }
                }
            ]
        }
    }

    // Different systray contents when there is no accounts
    Rectangle {
        visible: !hasAccounts
        width: parent.width - 2
        height: parent.height - 2
        anchors.centerIn: parent
        z: 5
        color: "white"

        ColumnLayout {
            width: parent.width * 3/4
            anchors.centerIn: parent

            IconLabel {
                icon: MdiFont.Icon.accountPlus
                size: 96
                Layout.alignment: Qt.AlignHCenter
                onClicked: api.show_settings("Accounts")
            }

            ScaledText {
                text: qsTr("NO_ACCOUNT") + tl.tr
                font {
                    pointSize: point_size * 1.2
                    weight: Font.Bold
                }
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

            Link {
                text: qsTr("OPEN_SETTINGS") + tl.tr
                font.pointSize: point_size * 1.2
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 50
                onClicked: api.show_settings("Accounts")
            }

            Link {
                text: qsTr("QUIT") + tl.tr
                font.pointSize: point_size * 1.2
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 10
                onClicked: {
                    application.hide_systray()
                    application.quit()
                }
            }
        }
    }

    // Update confirmation popup
    ConfirmPopup {
        id: updatePopup
        property string version
        property string channel

        message: qsTr("CONFIRM_UPDATE_MESSAGE").arg(channel).arg(version) + tl.tr
        onOk: {
            updatePopup.close()
            systray.appUpdate(version)
        }
    }
}
