import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: control

    ColumnLayout {
        id: features_layout
        width: parent.width * 0.9
        anchors {
            top: parent.top
            left: parent.left
            topMargin: 30
            leftMargin: 30
        }
        spacing: 10
        property var features_lst: api.get_features_list()

        ScaledText {
            text: qsTr("SECTION_FEATURES_DESC") + tl.tr
            color: secondaryText
            width: parent.width
            Layout.bottomMargin: 20
            Layout.maximumWidth: 570
            wrapMode: Text.WordWrap
        }

        Repeater {
            model: features_layout.features_lst.length
            delegate : GridLayout {
                columns: 1
                rowSpacing: 20

                GridLayout {
                    columns: 1
                    rowSpacing: 2
                    NuxeoSwitch {
                        property var item: features_layout.features_lst[index]
                        property var sup_tag: " <sup><font color='red'>" + qsTr("BETA") + "<font></<sup>" + tl.tr

                        text: item[0] + (beta_features.includes(item[1]) ? sup_tag: "")
                        checked: manager.get_feature_state(item[1])
                        enabled: !disabled_features.includes(item[1])
                        onClicked: manager.set_feature_state(item[1], checked)
                        Layout.leftMargin: -5
                    }
                    ScaledText {
                        text: qsTr(features_layout.features_lst[index][2]) + tl.tr
                        color: secondaryText
                        width: parent.width
                        Layout.maximumWidth: 570
                        Layout.leftMargin: 33
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
        ScaledText {
            text: qsTr("SECTION_FEATURES_BETA") + tl.tr
            color: secondaryText
            width: parent.width
            Layout.topMargin: 40
            Layout.maximumWidth: 570
            textFormat: Text.RichText
            wrapMode: Text.WordWrap
        }
    }
}
