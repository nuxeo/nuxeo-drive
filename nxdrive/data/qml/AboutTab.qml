import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
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
                sourceSize.width: 80
                sourceSize.height: 80
            }

            ColumnLayout {
                ScaledText {
                    text: nuxeoVersionText
                    color: primaryText
                    font {
                        pointSize: point_size * 1.8
                        weight: Font.Bold
                    }
                }
                SelectableText {
                    text: modulesVersionText
                    color: secondaryText
                }
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
            font.family: "Courier"
            color: primaryText
            text: "The source code of Nuxeo Drive is available under the LGPL 2.1." +
                  "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html\n\n" +
                  "Nuxeo Drive depends on those components:" +
                  "- Qt: GNU Lesser General Public License, version 3" +
                  "- PyQt: GNU General Public License, version 2 or 3\n\n" +
                  "Thus any code written on the top of Nuxeo Drive must be distributed" +
                  "under the terms of a GPL compliant license."
        }
    }
}
