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
    var icon = NSImage(named: NSImage.Name(rawValue: "icon_64.png"))
    let watchFolderNotif = NSNotification.Name("org.nuxeo.drive.watchFolder")
    let triggerWatchNotif = NSNotification.Name("org.nuxeo.drive.triggerWatch")
    let syncStatusNotif = NSNotification.Name("org.nuxeo.drive.syncStatus")
    let fileStatus = FileStatus()

    let badges: [(image: NSImage, label: String, identifier: String)] = [
        (image: #imageLiteral(resourceName: "emblem-drive_sync.png"), label: "Synchronized", identifier: "synced"),
        (image: #imageLiteral(resourceName: "emblem-drive_pending.png"), label: "Syncing", identifier: "syncing"),
        (image: #imageLiteral(resourceName: "emblem-drive_conflict.png"), label: "Conflicted", identifier: "conflicted"),
        (image: #imageLiteral(resourceName: "emblem-drive_error.png"), label: "In Error", identifier: "error"),
        (image: #imageLiteral(resourceName: "emblem-drive_locked.png"), label: "Locked", identifier: "locked"),
        (image: #imageLiteral(resourceName: "emblem-drive_not_sync.png"), label: "Not Synchronized", identifier: "unsynced")
    ]

    override init() {
        //NSLog("FinderSync() launched from %@", Bundle.main.bundlePath as NSString)
        super.init()

        // Upon startup, we are not watching any directories
        FIFinderSyncController.default().directoryURLs = []
        for badge in self.badges {
            FIFinderSyncController.default().setBadgeImage(
                badge.image,
                label: badge.label,
                forBadgeIdentifier: badge.identifier
            )
        }

        DistributedNotificationCenter.default.addObserver(self,
                                                          selector: #selector(receiveSyncStatus),
                                                          name: self.syncStatusNotif,
                                                          object: nil)
        // We add an observer to listen to watch notifications from the main application
        DistributedNotificationCenter.default.addObserver(self,
                                                          selector: #selector(setWatchedFolders),
                                                          name: self.watchFolderNotif,
                                                          object: nil)

        let triggerURL = URL(string: "nxdrive://trigger_watch")
        NSWorkspace.shared.open(triggerURL!)

        // Set up images for our badge identifiers.
        // For demonstration purposes, this uses off-the-shelf images.
        /*
        FIFinderSyncController.default().setBadgeImage(NSImage(named: .colorPanel)!,
                                                       label: "Status One",
                                                       forBadgeIdentifier: "One")
        FIFinderSyncController.default().setBadgeImage(NSImage(named: .caution)!,
                                                       label: "Status Two",
                                                       forBadgeIdentifier: "Two")
        */
    }

    deinit {
        // Remove the observer from the system upon shutdown
        DistributedNotificationCenter.default.removeObserver(self,
                                                             name: self.syncStatusNotif,
                                                             object: nil)
        DistributedNotificationCenter.default.removeObserver(self,
                                                             name: self.watchFolderNotif,
                                                             object: nil)
    }

    @objc func setWatchedFolders(notification: NSNotification) {
        // Retrieve the operation (watch/unwatch) and the path from the notification dictionary
        if let operation = notification.userInfo!["operation"], let path = notification.userInfo!["path"] {
            let target = URL(fileURLWithPath: path as! String)
            if operation as! String == "watch" {
                NSLog("Now watching: %@", target.path as NSString)
                FIFinderSyncController.default().directoryURLs.insert(target)
            } else if operation as! String == "unwatch" {
                NSLog("Now ignoring: %@", target.path as NSString)
                FIFinderSyncController.default().directoryURLs.remove(target)
            }
        }
    }

    @objc func receiveSyncStatus(notification: NSNotification) {
        // Retrieve the operation status and the path from the notification dictionary
        if let status = notification.userInfo!["status"], let path = notification.userInfo!["path"] {
            //NSLog("Receiving sync status of %@ to %@", path as! NSString, status as! NSString)
            fileStatus.insertStatus(status as! String, for: path as! String)
            setSyncStatus(path: path as! String, status: status as! String)
        }
    }

    func setSyncStatus(path: String, status: String) {
        // Set the badge identifier for the target file
        //NSLog("Setting sync status of %@ to %@", path, status)
        let target = URL(fileURLWithPath: path)
        FIFinderSyncController.default().setBadgeIdentifier(status, for: target)
    }

    // Primary Finder Sync protocol methods

    override func beginObservingDirectory(at url: URL) {
        // The user is now seeing the container's contents.
        // If they see it in more than one view at a time, we're only told once.
        //NSLog("beginObservingDirectoryAtURL: %@", url.path as NSString)
    }

    override func endObservingDirectory(at url: URL) {
        // The user is no longer seeing the container's contents.
        //NSLog("endObservingDirectoryAtURL: %@", url.path as NSString)
    }

    override func requestBadgeIdentifier(for url: URL) {
        // Badges on synced files and folders
        //NSLog("requestBadgeIdentifierForURL: %@", url.path as NSString)
        if let status = fileStatus.getStatus(for: url.path as String) {
            setSyncStatus(path: url.path as String, status: status)
        } else {
            getSyncStatus(target: url)
        }
    }

    // Toolbar

    /*
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
    */

    // Context menu, also toolbar menu, if previous code is uncommented

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

    func getSyncStatus(target: URL?) {
        // Called by requestBadgeIdentifier to ask Drive for a status
        //NSLog("sync_status: target: %@", target!.path as NSString)
        openNXUrl(command: "sync_status", target: target)
    }

    @IBAction func openInBrowser(_ sender: AnyObject?) {
        // Event fired by "Access online" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            //NSLog("openInBrowser: target: %@", item.path as NSString)
            openNXUrl(command: "access", target: item)
        }
    }

    @IBAction func copyShareLink(_ sender: AnyObject?) {
        // Event fired by "Copy share-link" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            //NSLog("copyShareLink: target: %@", item.path as NSString)
            openNXUrl(command: "share_link", target: item)
        }
    }

    func openNXUrl(command: String, target: URL?) {
        // Protocol URL "nxdrive://" trigger
        guard let targetPath = target?.path else {
            return
        }
        //NSLog("Target path is %@", targetPath)
        let request = String(format: "nxdrive://%@/%@", command, targetPath.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)!)
        let url = URL(string: request)
        //NSLog("Launching URL %@", request)
        NSWorkspace.shared.open(url!)
    }

}
