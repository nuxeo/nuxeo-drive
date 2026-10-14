import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
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
                    text: driveVersionText
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
                SelectableText {
                    text: deviceIdText
                    color: secondaryText
                }
            }
        }

        IconLink {
            text: qsTr("UPDATES_LINK") + tl.tr
            icon: MdiFont.Icon.update
            url: api.get_update_url()
        }

        OpenSourceAttribution {
            linkText: qsTr("OPEN_SOURCE_ATTRIBUTION") + tl.tr
            icon: MdiFont.Icon.messageReplyText
            serverType: SERVER_TYPE
        }

        LicenseAgreement {
            linkText: qsTr("LICENSE_AGREEMENT_ABOUT_TAB") + tl.tr
            icon: MdiFont.Icon.messageReplyText
            serverType: SERVER_TYPE
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
            property string appName: SERVER_TYPE === "ALFRESCO" ? "Hyland Drive for Alfresco" : "Nuxeo Drive"
            text: "The source code of " + appName + " is available under the LGPL 2.1." +
                  "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html\n\n" +
                  appName + " depends on those components:" +
                  "- Qt: GNU Lesser General Public License, version 3" +
                  "- PyQt: GNU General Public License, version 2 or 3\n\n" +
                  "Thus any code written on the top of " + appName + " must be distributed" +
                  "under the terms of a GPL compliant license.\n\n" +
                  "©2026 Hyland Software, Inc. and its affiliates. All rights reserved. " +
                  "All Hyland product names are registered or unregistered trademarks of Hyland Software, Inc. or its affiliates."
        }
    }
}
