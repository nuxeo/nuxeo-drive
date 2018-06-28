import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control


    Rectangle {
        width: parent.width - 100; height: parent.height - 50

        anchors {
            top: parent.top
            horizontalCenter: parent.horizontalCenter
            topMargin: -2
        }

        Rectangle {
            id: info
            width: parent.width; height: 150; z: 10
            
            Text {
                id: nuxeoVersion
                text: nuxeoVersionText
                font { weight: Font.Bold; pointSize: 24 }

                anchors {
                    top: parent.top
                    left: parent.left
                    topMargin: 50
                }
            }

            Text {
                id: modulesVersion
                text: modulesVersionText

                anchors {
                    top: nuxeoVersion.bottom
                    left: parent.left
                }
            }
            
            IconLink {
                id: githubLink
                text: "See the source"
                icon: MdiFont.Icon.githubCircle
                url: "https://github.com/nuxeo/nuxeo-drive"
                anchors {
                    top: modulesVersion.bottom
                    left: parent.left
                    topMargin: 10
                }
            }
            
            IconLink {
                id: updateLink
                text: "See updates"
                icon: MdiFont.Icon.download
                url: api.get_update_url()
                anchors {
                    top: githubLink.bottom
                    left: parent.left
                }
            }
        }

        Flickable {
            width: parent.width; height: 200
            contentHeight: licenseText.height
            ScrollBar.vertical: ScrollBar { active: true }

            anchors {
                top: info.bottom
                horizontalCenter: parent.horizontalCenter
                topMargin: 10
            }
            Text {
                id: licenseText
                
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
}