import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

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
    function getRole(role) { return model.get(currentIndex, role) }
}
