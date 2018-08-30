import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    ColumnLayout {
        id: info

        anchors {
            top: parent.top
            left: parent.left
            topMargin: 30
            leftMargin: 30
        }
        spacing: 10

        RowLayout {
            Layout.leftMargin: -10
            Image {
                source: "../icons/app_icon.svg"
                fillMode: Image.PreserveAspectFit
                sourceSize.width: 60
                sourceSize.height: 60
            }

            ColumnLayout {
                ScaledText {
                    text: nuxeoVersionText
                    pointSize: 20; font.weight: Font.Bold
                }
                ScaledText { text: modulesVersionText; color: mediumGray }
            }
        }

        IconLink {
            text: qsTr("SOURCE_LINK") + tl.tr
            icon: MdiFont.Icon.codeTags
            url: "https://github.com/nuxeo/nuxeo-drive"
        }

        IconLink {
            text: qsTr("UPDATES_LINK") + tl.tr
            icon: MdiFont.Icon.update
            url: api.get_update_url()
        }

        IconLink {
            text: qsTr("FEEDBACK_LINK") + tl.tr
            icon: MdiFont.Icon.messageReplyText
            url: "https://portal.prodpad.com/089ed2a6-c892-11e7-aea6-0288f735e5b9"
        }
    }

    Flickable {
        width: parent.width * 0.9; height: 200
        anchors {
            top: info.bottom
            horizontalCenter: parent.horizontalCenter
            topMargin: 50
        }

        clip: true
        contentHeight: licenseText.height

        ScaledText {
            id: licenseText
            width: parent.width
            wrapMode: Text.WordWrap
            font.family: 'monospace'
            pointSize: 12

            Component.onCompleted: {
                var request = new XMLHttpRequest();
                request.open('GET', 'GPL.txt');
                request.onreadystatechange = function(event) {
                    if (request.readyState == XMLHttpRequest.DONE) {
                        licenseText.text = request.responseText;
                    }
                }
                request.send();
            }
        }
    }
}
