//
//  FinderSync.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 28/02/2018.
//
//  Contributors:
//      Mickaël Schoentgen
//
//  Copyright © 2018 Nuxeo. All rights reserved.
//

import Cocoa
import FinderSync

class FinderSync: FIFinderSync {

    var myFolderURL = URL(fileURLWithPath: "/Users/tiger-222")
    var icon = NSImage(named: NSImage.Name(rawValue: "icon_64.png"))

    override init() {
        super.init()

        NSLog("FinderSync() launched from %@", Bundle.main.bundlePath as NSString)

        // Set up the directory we are syncing.
        FIFinderSyncController.default().directoryURLs = [self.myFolderURL]

        // Set up images for our badge identifiers. For demonstration purposes, this uses off-the-shelf images.
        //FIFinderSyncController.default().setBadgeImage(NSImage(named: .colorPanel)!,
        //                                               label: "Status One",
        //                                               forBadgeIdentifier: "One")
        //FIFinderSyncController.default().setBadgeImage(NSImage(named: .caution)!,
        //                                               label: "Status Two",
        //                                               forBadgeIdentifier: "Two")
    }

    // Primary Finder Sync protocol methods

    override func beginObservingDirectory(at url: URL) {
        // The user is now seeing the container's contents.
        // If they see it in more than one view at a time, we're only told once.
        NSLog("beginObservingDirectoryAtURL: %@", url.path as NSString)
    }

    override func endObservingDirectory(at url: URL) {
        // The user is no longer seeing the container's contents.
        NSLog("endObservingDirectoryAtURL: %@", url.path as NSString)
    }

    override func requestBadgeIdentifier(for url: URL) {
        // Badges on synced files and folders
        NSLog("requestBadgeIdentifierForURL: %@", url.path as NSString)
        // For demonstration purposes, this picks one of our two badges, or no badge at all, based on the filename.
        // Inspiration: https://github.com/haiwen/seafile-client/blob/master/fsplugin/FinderSync.mm
        //let whichBadge = abs(url.path.hash) % 3
        //let badgeIdentifier = ["", "One", "Two"][whichBadge]
        //FIFinderSyncController.default().setBadgeIdentifier(badgeIdentifier, for: url)
    }

    // Toolbar and menu

    override var toolbarItemName: String {
        return "Nuxeo Drive"
    }

    override var toolbarItemToolTip: String {
        return "Nuxeo Drive: Click the button for a menu"
    }

    override var toolbarItemImage: NSImage {
        // Set the toolbar icon
        return self.icon!
    }

    override func menu(for menuKind: FIMenuKind) -> NSMenu {
        // Produce a menu for the extension
        let menu = NSMenu(title: "Nuxeo Drive")

        // Access online
        let item1 = NSMenuItem(title: "Access online",
                               action: #selector(openInBrowser(_:)),
                               keyEquivalent: "A")
        item1.image = self.icon
        menu.addItem(item1)

        // Copy share-link
        let item2 = NSMenuItem(title: "Copy share-link",
                               action: #selector(copyShareLink(_:)),
                               keyEquivalent: "C")
        item2.image = self.icon
        menu.addItem(item2)

        return menu
    }

    @IBAction func openInBrowser(_ sender: AnyObject?) {
        // Event fired by "Access online" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            NSLog("openInBrowser: target: %@", item.path as NSString)
            openNXUrl(command: "access", target: item)
        }
    }

    @IBAction func copyShareLink(_ sender: AnyObject?) {
        // Event fired by "Copy share-link" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            NSLog("copyShareLink: target: %@", item.path as NSString)
            openNXUrl(command: "share_link", target: item)
        }
    }

    func openNXUrl(command: String, target: URL?) {
        // Protocol URL "nxdrive://" trigger
        guard let targetPath = target?.path else {
            return
        }
        NSLog("Target path is %@", targetPath)
        let request = String(format: "nxdrive://%@/%@", command, targetPath)
        let url = URL(string: request.replacingOccurrences(of: " ", with: "%20"))
        NSLog("Launching URL %@", request)
        NSWorkspace.shared.open(url!)
    }

}
