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
            property string productName: SERVER_TYPE === "NUXEO" ? "Nuxeo" : "Alfresco"
            text: appName + " includes third-party open source components, which are licensed under their own terms.\n" +
                  "See the Open Source Attribution Notice for the full list of components and their licences.\n" +
                  "©2026 Hyland. " + productName + ", Hyland, the H design, and Hyland product names " +
                  "are registered and/or unregistered trademarks of Hyland and its affiliates in the United States and other countries."
        }
    }
}
