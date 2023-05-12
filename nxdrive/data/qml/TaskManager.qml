import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "icon-font/Icon.js" as MdiFont



Rectangle {
    id: taskManager
    anchors.fill: parent

    property string engineUid: ""
    property int activeSessionsCount: 0
    property int completedSessionsCount: 0
    property double startTime: 0.0

    signal setEngine(string uid)
    
    onSetEngine: {
        engineUid = uid
    }

    TabBar {
        id: bar
        width: parent.width
        height: 50
        spacing: 0

        anchors.top: buttonzone.bottom

        SettingsTab {
            text: qsTr("Tasks") + tl.tr
            barIndex: bar.currentIndex;
            index: 0
            anchors.top: parent.top
        }
        
   }

   Text {
            anchors.fill: parent
            horizontalAlignment: Qt.AlignHCenter
            verticalAlignment: Qt.AlignVCenter
            height: 100
            /*textFormat: Text.RichText*/
            text: api.get_title(engineUid)
            font.pointSize: point_size * 1.2
            color: primaryText
        }
}
