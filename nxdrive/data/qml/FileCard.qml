import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

ShadowRectangle {
    id: control

    signal resolved()
    signal ignored()

    property var fileData
    property string type: fileData.state == "conflicted" ? "conflict" : "error"

    width: parent.width; height: cardContent.height + 40
    samples: 60; vOffset: 3
    anchors.horizontalCenter: parent.horizontalCenter

    RowLayout {
        id: cardContent
        width: parent.width - 40
        anchors.centerIn: parent
        spacing: 10

        Rectangle {
            width: 10; height: 10; radius: 10
            color: type == "conflict" ? orange : red
            Layout.alignment: Qt.AlignTop | Qt.AlignRight
        }

        ColumnLayout {
            spacing: 10

            ScaledText {
                id: fileName
                text: fileData.name + (fileData.folderish ? "/" : "")
                font { pointSize: 16 / ratio; weight: Font.Bold }
            }

            ScaledText {
                id: errorReason
                visible: type != "conflict"
                property string reason: type == "ignored" ? "IGNORE_REASON_" : "ERROR_REASON_"
                Layout.fillWidth: true

                text: qsTr(reason + fileData.last_error) + tl.tr
                wrapMode: Text.WordWrap
                lineHeight: 1.15
            }

            ScaledText {
                id: errorDetailsTitle
                text: qsTr("TECHNICAL_DETAILS") + tl.tr
                visible: errorDetails.visible
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            ScaledText {
                id: errorDetails
                text: fileData.details
                visible: type != "conflict" && text
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            ScaledText {
                id: parentPath
                text: qsTr("FILE_PATH").arg(fileData.local_parent_path) + tl.tr
                color: mediumGray
                MouseArea {
                    anchors.fill: parent
                    onClicked: api.open_local(fileData.local_parent_path)
                }
            }

            ScaledText {
                id: lastContributor
                text: qsTr("LAST_CONTRIBUTOR").arg(fileData.last_contributor) + tl.tr
                color: mediumGray
            }

            ScaledText {
                id: lastSynchronized

                property string date: fileData.last_sync_date ? fileData.last_sync_date : fileData.last_remote_update

                text: qsTr("LAST_SYNCHRONIZED").arg(date) + tl.tr
                color: mediumGray
            }

            RowLayout {
                spacing: 20

                Link {
                    id: openLocalLink
                    text: qsTr("OPEN_LOCAL") + tl.tr
                    visible: type == "conflict"
                    onClicked: api.open_local(fileData.local_path)
                }

                Link {
                    id: openRemoteLink
                    text: qsTr("OPEN_REMOTE") + tl.tr
                    visible: type == "conflict"
                    onClicked: api.open_remote(fileData.remote_ref, fileData.remote_name)
                }

                NuxeoComboBox {
                    id: resolveAction
                    displayText: qsTr("RESOLVE") + tl.tr
                    visible: type == "conflict"
                    font.pointSize: 14 / ratio

                    model: ["CONFLICT_USE_LOCAL", "CONFLICT_USE_REMOTE"]

                    delegate: ItemDelegate {
                        id: conflictDelegate
                        width: resolveAction.width
                        contentItem: ScaledText {
                            anchors.fill: parent
                            text: qsTr(modelData) + tl.tr
                            leftPadding: 10
                            elide: Text.ElideRight
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
                            api.resolve_with_local(fileData.id)
                        } else {
                            api.resolve_with_remote(fileData.id)
                        }
                        control.resolved()
                    }
                }

                Link {
                    id: retry
                    text: qsTr("CONFLICT_RETRY") + tl.tr
                    visible: type == "error"
                    onClicked: api.retry_pair(fileData.id)
                }

                Link {
                    text: qsTr("IGNORE_PAIR") + tl.tr
                    visible: type == "error"
                    onClicked: {
                        api.unsynchronize_pair(fileData.id, fileData.last_error)
                        control.ignored()
                    }
                }
            }
        }
    }
}
