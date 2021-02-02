import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ShadowRectangle {
    id: control

    signal resolved()
    signal ignored()

    property variant fileData
    property string type: fileData.state == "conflicted" ? "conflict" : "error"

    width: parent ? parent.width - 10 : 0
    height: cardContent.height + 40
    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined

    RowLayout {
        id: cardContent
        width: parent.width - 40
        anchors.centerIn: parent
        spacing: 10

        // Color badge
        Rectangle {
            width: 10; height: 10; radius: 10
            color: type == "conflict" ? warningContent : errorContent
            Layout.alignment: Qt.AlignTop | Qt.AlignRight
        }

        ColumnLayout {
            spacing: 10

            // Document name
            ScaledText {
                id: fileName
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: fileData.name + (fileData.folderish ? "/" : "")
                font {
                    pointSize: point_size * 1.2
                    weight: Font.Bold
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: api.open_document(engineUid, fileData.id)
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                }
            }

            // Conflict/Error reason
            SelectableText {
                id: errorReason
                visible: type != "conflict"
                property string reason: type == "ignored" ? "IGNORE_REASON_" : "ERROR_REASON_"
                Layout.fillWidth: true

                text: qsTr(reason + fileData.last_error) + tl.tr
                wrapMode: Text.WordWrap
            }

            SelectableText {
                id: errorDetailsTitle
                text: qsTr("TECHNICAL_DETAILS") + tl.tr
                visible: errorDetails.visible
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            // Conflict/Error details
            SelectableText {
                id: errorDetails
                font.family: "Courier"
                text: fileData.last_error_details
                visible: type != "conflict" && text
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            // Parent path of the document
            SelectableText {
                id: parentPath
                text: qsTr("FILE_PATH").arg(fileData.local_parent_path) + tl.tr
                color: mediumGray
                Layout.fillWidth: true
            }

            // Last contributor
            SelectableText {
                id: lastContributor
                text: qsTr("LAST_CONTRIBUTOR").arg(fileData.last_contributor) + tl.tr
                Layout.fillWidth: true
                color: mediumGray
            }

            // Last synchronization date
            SelectableText {
                id: lastSynchronized

                property string date: fileData.last_sync_date ? fileData.last_sync_date : fileData.last_remote_update

                text: qsTr("LAST_SYNCHRONIZED").arg(date) + tl.tr
                Layout.fillWidth: true
                color: mediumGray
            }

            // Possible actions list
            RowLayout {
                spacing: 20

                // Open the local file
                Link {
                    id: openLocalLink
                    text: qsTr("OPEN_LOCAL") + tl.tr
                    visible: type == "conflict"
                    onClicked: api.open_local(engineUid, fileData.local_path)
                }

                // Open the remote file
                Link {
                    id: openRemoteLink
                    text: qsTr("OPEN_REMOTE") + tl.tr
                    visible: type == "conflict"
                    onClicked: api.open_remote_document(engineUid, fileData.remote_ref, fileData.remote_name)
                }

                // Resolution options popup list
                NuxeoComboBox {
                    id: resolveAction
                    displayText: qsTr("RESOLVE") + tl.tr
                    visible: type == "conflict"
                    width: 170

                    model: ["CONFLICT_USE_LOCAL", "CONFLICT_USE_REMOTE"]

                    delegate: ItemDelegate {
                        id: conflictDelegate
                        width: resolveAction.width
                        contentItem: ScaledText {
                            anchors.fill: parent
                            text: qsTr(modelData) + tl.tr
                            leftPadding: 10
                            verticalAlignment: Text.AlignVCenter

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: conflictDelegate.clicked()
                            }
                        }
                        highlighted: resolveAction.highlightedIndex === index
                    }
                    onActivated: {
                        if (resolveAction.currentIndex == 0) {
                            api.resolve_with_local(engineUid, fileData.id)
                        } else {
                            api.resolve_with_remote(engineUid, fileData.id)
                        }
                        control.resolved()
                    }
                }

                // Retry button
                Link {
                    id: retry
                    text: qsTr("CONFLICT_RETRY") + tl.tr
                    visible: type == "error" && fileData.last_error != "DEDUP"
                    onClicked: api.retry_pair(engineUid, fileData.id)
                }

                // Ignore button
                Link {
                    text: qsTr("IGNORE_PAIR") + tl.tr
                    visible: type == "error"
                    onClicked: {
                        api.ignore_pair(engineUid, fileData.id, fileData.last_error)
                        control.ignored()
                    }
                }
            }
        }
    }
}
