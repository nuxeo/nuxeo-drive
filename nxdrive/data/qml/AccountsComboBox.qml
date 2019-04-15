import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

NuxeoComboBox {
    id: control
    model: EngineModel
    textRole: "account"

    TextMetrics { id: textMetrics; font: control.font }
    Component.onCompleted: {
        if (model.count > 0) { currentIndex = 0; adaptWidth() }
    }

    function adaptWidth() {
        for(var i = 0; i < EngineModel.count; i++){
            textMetrics.text = EngineModel.get(i, control.textRole)
            modelWidth = Math.max(textMetrics.width, modelWidth)
        }
    }
    function getRole(role) { return model.get(currentIndex, role) }
}
