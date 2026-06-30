"""Alfresco-specific macOS FinderSync configuration."""

ALFRESCO_AGENT_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    '<plist version="1.0">'
    "<dict>"
    "<key>Label</key>"
    "<string>org.alfresco.drive.agentlauncher</string>"
    "<key>RunAtLoad</key>"
    "<true/>"
    "<key>Program</key>"
    "<string>%s</string>"
    "</dict>"
    "</plist>"
)

ALFRESCO_FINDERSYNC_ID_SUFFIX = "AlfrescoFinderSync"
ALFRESCO_FINDERSYNC_APPEX = "AlfrescoFinderSync.appex"
