import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

NuxeoComboBox {
    id: control
    model: EngineModel
    textRole: "remote_user"

    // Use elide when text is too long
    elideStyle: Text.ElideRight

    TextMetrics {
        id: textMetrics
        font: control.font
    }

    Component.onCompleted: {
        if (model.count > 0) {
            currentIndex = 0
            adaptWidth()
            application.set_current_account(getRole("uid"))
        }
    }

    // Whenever the selected account changes -- whether by user
    // interaction or programmatically (e.g. after an account is
    // added/removed) -- notify the Application so it can scope the
    // shared systray models (transfers, recent files, sync/error
    // indicator, tray icon) to the newly selected profile.
    // See NXDRIVE-3246.
    onCurrentIndexChanged: {
        if (currentIndex >= 0) {
            var uid = getRole("uid")
            if (uid) {
                application.set_current_account(uid)
            }
        }
    }

    function adaptWidth() {
        // Compute the dropdown list width based on the longest item.
        for (var i = 0; i < EngineModel.count; i++) {
            textMetrics.text = EngineModel.get(i, control.textRole)
            modelWidth = Math.max(textMetrics.width, modelWidth)
        }
    }

    delegate: ItemDelegate {
                width: control.width
                contentItem: ScaledText {
                    text: qsTr(remote_user) + tl.tr
                    verticalAlignment: Text.AlignVCenter
                }
                highlighted: control.highlightedIndex === index
                background: Rectangle {
                    color: highlighted ? popupBackgroundHighlighted : "transparent"
                }
            }
    function getRole(role) { return model.get(currentIndex, role) }
}
