import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "icon-font/Icon.js" as MdiFont

Window {
    id: collectionWindow
    objectName: "collectionsFavoritesWindow"
    title: qsTr("Collections & Favorites")
    width: 520
    height: 580
    minimumWidth: 460
    minimumHeight: 520
    visible: false
    color: "white"

    property string accountUid: ""
    property var collections: []
    property var selectionsByAccount: ({})
    property var selectedCollectionIds: []
    property bool syncFavorites: false
    property bool collectionsLoading: false
    property bool membersLoading: false
    property string collectionsError: ""
    property string membersError: ""
    property string activeCollectionId: ""
    property string activeCollectionName: ""
    property var collectionMembers: []
    property int requestSequence: 0
    property int collectionsRequest: 0
    property int membersRequest: 0
    property var navigationPath: []

    signal applied(string uid, var collectionIds, bool favorites)

    function restoreSelection() {
        var saved = selectionsByAccount[accountUid]
        selectedCollectionIds = saved ? saved.collectionIds.slice() : []
        syncFavorites = saved ? saved.favorites : false
    }

    function openForAccount(uid) {
        accountUid = uid
        restoreSelection()
        tabs.currentIndex = 0
        search.text = ""
        activeCollectionId = ""
        activeCollectionName = ""
        navigationPath = []
        collectionMembers = []
        membersLoading = false
        membersError = ""
        show()
        requestActivate()
        loadCollections()
    }

    function loadCollections() {
        collections = []
        collectionsError = ""
        collectionsLoading = true
        collectionsRequest = ++requestSequence
        api.load_collection_documents(accountUid, collectionsRequest, "")
    }

    function browseCollection(collectionId, collectionName) {
        api.log_collection_action(accountUid, "open_collection", collectionId)
        activeCollectionId = collectionId
        activeCollectionName = collectionName
        navigationPath = [{id: collectionId, name: collectionName}]
        loadCurrentFolder()
    }

    function browseFolder(folderId, folderName) {
        api.log_collection_action(accountUid, "open_folder", folderId)
        var updated = navigationPath.slice()
        updated.push({id: folderId, name: folderName})
        navigationPath = updated
        loadCurrentFolder()
    }

    function navigateTo(level) {
        if (level < 0 || level >= navigationPath.length)
            return
        navigationPath = navigationPath.slice(0, level + 1)
        loadCurrentFolder()
    }

    function loadCurrentFolder() {
        collectionMembers = []
        memberList.currentIndex = -1
        memberList.contentY = 0
        membersError = ""
        membersLoading = true
        membersRequest = ++requestSequence
        if (navigationPath.length > 1) {
            api.load_collection_folder(accountUid, membersRequest, activeCollectionId,
                navigationPath[navigationPath.length - 1].id)
        } else {
            api.load_collection_documents(accountUid, membersRequest, activeCollectionId)
        }
    }

    function selectCollection(collectionId, selected) {
        api.log_collection_action(
            accountUid, selected ? "select_collection" : "deselect_collection", collectionId)
        var updated = selectedCollectionIds.slice()
        var position = updated.indexOf(collectionId)
        if (selected && position < 0)
            updated.push(collectionId)
        else if (!selected && position >= 0)
            updated.splice(position, 1)
        selectedCollectionIds = updated
    }

    function applySelection() {
        selectionsByAccount[accountUid] = {
            collectionIds: selectedCollectionIds.slice(),
            favorites: syncFavorites
        }
        api.apply_collection_selection(accountUid, selectedCollectionIds.slice())
        applied(accountUid, selectedCollectionIds.slice(), syncFavorites)
        close()
    }

    onClosing: restoreSelection()

    Connections {
        target: api

        function onCollectionSearchFinished(uid, requestId, collectionId, documents, error) {
            if (!collectionWindow.visible || uid !== collectionWindow.accountUid)
                return
            if (!collectionId && requestId === collectionWindow.collectionsRequest) {
                collectionWindow.collectionsLoading = false
                collectionWindow.collectionsError = error ? qsTr("Could not load collections.") : ""
                collectionWindow.collections = JSON.parse(documents)
                collectionWindow.selectedCollectionIds = collectionWindow.collections
                    .filter(function(collection) { return collection.selected })
                    .map(function(collection) { return collection.id })
                collectionWindow.selectionsByAccount[uid] = {
                    collectionIds: collectionWindow.selectedCollectionIds.slice(),
                    favorites: collectionWindow.syncFavorites
                }
            } else if (collectionId === collectionWindow.activeCollectionId && requestId === collectionWindow.membersRequest) {
                collectionWindow.membersLoading = false
                collectionWindow.membersError = error ? qsTr("Could not load collection items.") : ""
                collectionWindow.collectionMembers = JSON.parse(documents)
            }
        }
    }

    Shortcut {
        sequence: "Escape"
        onActivated: collectionWindow.close()
    }

    Shortcut {
        sequence: "Alt+Left"
        enabled: navigationPath.length > 1 && tabs.currentIndex === 0
        onActivated: collectionWindow.navigateTo(collectionWindow.navigationPath.length - 2)
    }

    FontLoader {
        source: "icon-font/materialdesignicons-webfont.ttf"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        ScaledText {
            text: qsTr("Choose what to sync to this computer.")
            color: secondaryText
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }

        TabBar {
            id: tabs
            objectName: "collectionsFavoritesTabs"
            Layout.fillWidth: true
            background: Rectangle { color: "transparent" }

            Repeater {
                model: [qsTr("Collections"), qsTr("Favorites")]

                TabButton {
                    id: selectionTab
                    required property string modelData
                    text: modelData
                    implicitHeight: 40

                    contentItem: ScaledText {
                        text: selectionTab.text
                        color: selectionTab.checked ? focusedTab : unfocusedTab
                        font {
                            pointSize: point_size * 1.2
                            weight: selectionTab.checked ? 600 : 400
                        }
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    background: Item {
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: selectionTab.checked ? 2 : 1
                            color: selectionTab.checked ? focusedUnderline : unfocusedUnderline
                        }
                    }
                }
            }
        }

        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                spacing: 12

                NuxeoInput {
                    id: search
                    objectName: "collectionSearch"
                    placeholderText: qsTr("Search collections...")
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    wrapMode: TextInput.NoWrap
                    clip: true
                }

                ListView {
                    id: collectionList
                    objectName: "collectionList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: collectionWindow.activeCollectionId ? 60 : 100
                    Layout.preferredHeight: collectionWindow.activeCollectionId ? 100 : 200
                    clip: true
                    model: collectionWindow.collections.filter(function(collection) {
                        return collection.name.toLowerCase().indexOf(search.text.toLowerCase()) >= 0
                    })
                    ScrollBar.vertical: ScrollBar {}

                    delegate: RowLayout {
                        required property var modelData
                        width: collectionList.width
                        height: 44
                        spacing: 12

                        NuxeoCheckBox {
                            Accessible.name: modelData.name
                            Layout.preferredWidth: 24
                            checked: collectionWindow.selectedCollectionIds.indexOf(modelData.id) >= 0
                            onClicked: collectionWindow.selectCollection(modelData.id, checked)
                        }

                        ItemDelegate {
                            text: modelData.name
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            onClicked: collectionWindow.browseCollection(modelData.id, modelData.name)

                            contentItem: ScaledText {
                                text: parent.text
                                color: secondaryText
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }

                            background: Item {}
                        }

                        ScaledText {
                            text: qsTr("%1 items").arg(modelData.file_count)
                            color: secondaryText
                            Layout.preferredWidth: 64
                            horizontalAlignment: Text.AlignRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        IconLabel {
                            icon: MdiFont.Icon.chevronRight
                            tooltip: qsTr("Open collection")
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 28
                            horizontalAlignment: Text.AlignHCenter
                            onClicked: collectionWindow.browseCollection(modelData.id, modelData.name)
                        }
                    }

                    ScaledText {
                        anchors.centerIn: parent
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        color: secondaryText
                        visible: collectionList.count === 0
                        text: collectionWindow.collectionsLoading ? qsTr("Loading collections...")
                            : collectionWindow.collectionsError ? collectionWindow.collectionsError
                            : search.text ? qsTr("No matching collections.") : qsTr("No collections available.")
                    }
                }

                NuxeoButton {
                    text: qsTr("Retry")
                    primary: false
                    visible: collectionWindow.collectionsError !== ""
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 36
                    onClicked: collectionWindow.loadCollections()
                }

                HorizontalSeparator {
                    visible: collectionWindow.activeCollectionId !== ""
                    Layout.fillWidth: true
                }

                RowLayout {
                    visible: collectionWindow.activeCollectionId !== ""
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    spacing: 8

                    IconLabel {
                        objectName: "collectionFolderBack"
                        icon: MdiFont.Icon.arrowLeft
                        tooltip: qsTr("Back to previous folder")
                        enabled: collectionWindow.navigationPath.length > 1
                        Layout.preferredWidth: 32
                        horizontalAlignment: Text.AlignHCenter
                        onClicked: collectionWindow.navigateTo(collectionWindow.navigationPath.length - 2)
                    }

                    Flickable {
                        id: breadcrumbViewport
                        objectName: "collectionBreadcrumbs"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: breadcrumbRow.width
                        contentHeight: height
                        flickableDirection: Flickable.HorizontalFlick
                        boundsBehavior: Flickable.StopAtBounds
                        onContentWidthChanged: Qt.callLater(function() {
                            breadcrumbViewport.contentX = Math.max(0, breadcrumbViewport.contentWidth - breadcrumbViewport.width)
                        })

                        Row {
                            id: breadcrumbRow
                            height: parent.height
                            spacing: 4

                            Repeater {
                                model: collectionWindow.navigationPath

                                Row {
                                    required property var modelData
                                    required property int index
                                    height: breadcrumbRow.height

                                    ScaledText {
                                        text: "/"
                                        visible: parent.index > 0
                                        height: parent.height
                                        color: secondaryText
                                        verticalAlignment: Text.AlignVCenter
                                    }

                                    ToolButton {
                                        id: breadcrumbButton
                                        objectName: "collectionBreadcrumb" + parent.index
                                        text: parent.modelData.name
                                        width: Math.min(160, breadcrumbLabel.implicitWidth + 20)
                                        height: parent.height
                                        enabled: parent.index < collectionWindow.navigationPath.length - 1
                                        onClicked: collectionWindow.navigateTo(parent.index)

                                        contentItem: ScaledText {
                                            id: breadcrumbLabel
                                            text: breadcrumbButton.text
                                            color: breadcrumbButton.enabled ? focusedUnderline : secondaryText
                                            elide: Text.ElideRight
                                            verticalAlignment: Text.AlignVCenter
                                        }

                                        background: Item {}

                                        NuxeoToolTip {
                                            text: breadcrumbButton.text
                                            visible: breadcrumbButton.hovered
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    id: memberTable
                    visible: collectionWindow.activeCollectionId !== ""
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 104
                    Layout.preferredHeight: 180
                    spacing: 0
                    property int typeColumnWidth: 72
                    property int locationColumnWidth: Math.floor(width * 0.3)

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        color: "transparent"

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 1
                            color: lightGray
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 22
                            spacing: 12

                            ScaledText {
                                text: qsTr("Name")
                                color: secondaryText
                                font.weight: 600
                                Layout.fillWidth: true
                            }

                            ScaledText {
                                text: qsTr("Type")
                                color: secondaryText
                                font.weight: 600
                                Layout.preferredWidth: memberTable.typeColumnWidth
                            }

                            ScaledText {
                                text: qsTr("Location")
                                color: secondaryText
                                font.weight: 600
                                Layout.preferredWidth: memberTable.locationColumnWidth
                            }
                        }
                    }

                    ListView {
                        id: memberList
                        objectName: "collectionMemberList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 72
                        clip: true
                        model: collectionWindow.collectionMembers
                        currentIndex: -1
                        ScrollBar.vertical: ScrollBar {}

                        delegate: ItemDelegate {
                            id: memberRow
                            required property var modelData
                            required property int index
                            text: modelData.name
                            width: memberList.width - 14
                            height: 36
                            leftPadding: 8
                            rightPadding: 8
                            onClicked: {
                                if (modelData.folderish)
                                    collectionWindow.browseFolder(modelData.id, modelData.name)
                                else
                                    memberList.currentIndex = index
                            }

                            contentItem: RowLayout {
                                spacing: 12

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    spacing: 8

                                    IconLabel {
                                        icon: memberRow.modelData.folderish ? MdiFont.Icon.folder : MdiFont.Icon.file
                                        enabled: false
                                        iconColorDisabled: secondaryIcon
                                        Layout.preferredWidth: 20
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    ScaledText {
                                        text: memberRow.modelData.name
                                        color: memberList.currentIndex === memberRow.index ? focusedUnderline : secondaryText
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        elide: Text.ElideRight
                                    }
                                }

                                ScaledText {
                                    objectName: "memberTypeCell"
                                    text: memberRow.modelData.type
                                    color: secondaryText
                                    Layout.preferredWidth: memberTable.typeColumnWidth
                                    Layout.maximumWidth: memberTable.typeColumnWidth
                                    elide: Text.ElideRight
                                }

                                ScaledText {
                                    objectName: "memberLocationCell"
                                    text: memberRow.modelData.path || ""
                                    color: secondaryText
                                    Layout.preferredWidth: memberTable.locationColumnWidth
                                    Layout.maximumWidth: memberTable.locationColumnWidth
                                    elide: Text.ElideMiddle
                                }
                            }

                            background: Rectangle {
                                color: "transparent"

                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 1
                                    color: lightGray
                                }
                            }

                            NuxeoToolTip {
                                text: memberRow.modelData.name + (memberRow.modelData.path ? "\n" + memberRow.modelData.path : "")
                                visible: memberRow.hovered
                            }
                        }

                        ScaledText {
                            anchors.centerIn: parent
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            color: secondaryText
                            visible: memberList.count === 0
                            text: collectionWindow.membersLoading ? qsTr("Loading collection items...")
                                : collectionWindow.membersError ? collectionWindow.membersError
                                : collectionWindow.navigationPath.length > 1 ? qsTr("This folder has no items.")
                                : qsTr("This collection has no items.")
                        }
                    }
                }

                NuxeoButton {
                    text: qsTr("Retry")
                    primary: false
                    visible: collectionWindow.membersError !== ""
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 36
                    onClicked: collectionWindow.loadCurrentFolder()
                }

                ScaledText {
                    text: qsTr('Collection entries appear as shortcuts under "My Collections" in your local Drive folder.')
                    color: secondaryText
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }
            }

            ColumnLayout {
                spacing: 12

                NuxeoCheckBox {
                    objectName: "syncFavoritesCheckBox"
                    text: qsTr("Sync my Favorites")
                    color: secondaryText
                    Layout.fillWidth: true
                    checked: collectionWindow.syncFavorites
                    onClicked: collectionWindow.syncFavorites = checked
                }

                ScaledText {
                    text: qsTr("Show favorite items in your local Drive.")
                    color: secondaryText
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Item { Layout.fillWidth: true }

            NuxeoButton {
                objectName: "cancelCollectionSelection"
                text: qsTr("Cancel")
                primary: false
                Layout.preferredWidth: 90
                Layout.preferredHeight: 36
                onClicked: collectionWindow.close()
            }

            NuxeoButton {
                objectName: "applyCollectionSelection"
                text: qsTr("Apply")
                Layout.preferredWidth: 90
                Layout.preferredHeight: 36
                onClicked: collectionWindow.applySelection()
            }
        }
    }
}
