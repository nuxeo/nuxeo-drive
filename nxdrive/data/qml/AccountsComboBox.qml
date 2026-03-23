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
