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
                    font { weight: Font.Bold; pointSize: 20 / ratio }
                }
                ScaledText { text: modulesVersionText; color: mediumGray }
            }
        }

        IconLink {
            text: "See the source"
            icon: MdiFont.Icon.codeTags
            url: "https://github.com/nuxeo/nuxeo-drive"
        }

        IconLink {
            text: "See updates"
            icon: MdiFont.Icon.update
            url: api.get_update_url()
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
            font.pointSize: 12 / ratio

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
