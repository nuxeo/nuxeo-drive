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
    let addr = "127.0.0.1"
    let port: Int = 50675
    var socket: SocketCom?

    let badges: [(image: NSImage, label: String, identifier: String)] = [
        (image: #imageLiteral(resourceName: "badge_synced.png"), label: "Synchronized", identifier: "synced"),
        (image: #imageLiteral(resourceName: "badge_syncing.png"), label: "Syncing", identifier: "syncing"),
        (image: #imageLiteral(resourceName: "badge_conflicted.png"), label: "Conflicted", identifier: "conflicted"),
        (image: #imageLiteral(resourceName: "badge_error.png"), label: "In Error", identifier: "error"),
        (image: #imageLiteral(resourceName: "badge_locked.png"), label: "Locked", identifier: "locked"),
        (image: #imageLiteral(resourceName: "badge_unsynced.png"), label: "Not Synchronized", identifier: "unsynced")

    ]

    override init() {
        //NSLog("FinderSync() launched from \(Bundle.main.bundlePath)")
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
        self.socket = SocketCom(addr: addr, port: port)

        triggerWatch()
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
                NSLog("Now watching: \(target.path)")
                FIFinderSyncController.default().directoryURLs.insert(target)
            } else if operation as! String == "unwatch" {
                NSLog("Now ignoring: \(target.path)")
                FIFinderSyncController.default().directoryURLs.remove(target)
            }
        }
    }

    @objc func receiveSyncStatus(notification: NSNotification) {
        // Retrieve the operation status and the path from the notification dictionary
        if let statuses = notification.userInfo!["statuses"] as! Array<Dictionary<String, String>>? {
            for item in statuses {
                let path = item["path"]!
                let status = item["status"]!
                fileStatus.insertStatus(status, for: path)
                setSyncStatus(path: path, status: status)
            }
        }
//        if let status = notification.userInfo!["status"], let path = notification.userInfo!["path"] {
//            //NSLog("Receiving sync status of \(path) to \(status)")
//            fileStatus.insertStatus(status as! String, for: path as! String)
//            setSyncStatus(path: path as! String, status: status as! String)
//        }
    }

    func setSyncStatus(path: String, status: String) {
        // Set the badge identifier for the target file
        //NSLog("Setting sync status of \(path) to \(status)")
        let target = URL(fileURLWithPath: path)
        FIFinderSyncController.default().setBadgeIdentifier(status, for: target)
    }

    // Primary Finder Sync protocol methods

    override func beginObservingDirectory(at url: URL) {
        // The user is now seeing the container's contents.
        // If they see it in more than one view at a time, we're only told once.
        //NSLog("beginObservingDirectoryAtURL: \(url.path)")
        let path = url.path as String
        if fileStatus.shouldVisit(path) {
            //NSLog("should visit: \(path)")
            getSyncStatus(target: url)
            fileStatus.visit(path)
        }
    }

    override func endObservingDirectory(at url: URL) {
        // The user is no longer seeing the container's contents.
        //NSLog("endObservingDirectoryAtURL: \(url.path)")
    }

    override func requestBadgeIdentifier(for url: URL) {
        // Badges on synced files and folders
        //NSLog("requestBadgeIdentifierForURL: \(url.path)")
        if let status = fileStatus.getStatus(for: url.path as String) {
            setSyncStatus(path: url.path as String, status: status)
        } else {
            let path = url.deletingLastPathComponent().path as String
            //NSLog("Removing visit of \(url.path) parent")
            fileStatus.removeVisit(path)
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
                               action: #selector(accessOnline(_:)),
                               keyEquivalent: "A")
        item1.image = self.icon
        menu.addItem(item1)

        // Copy share-link
        let item2 = NSMenuItem(title: "Copy share-link",
                               action: #selector(copyShareLink(_:)),
                               keyEquivalent: "C")
        item2.image = self.icon
        menu.addItem(item2)

        // Edit metadata
        let item3 = NSMenuItem(title: "Edit metadata",
                               action: #selector(editMetadata(_:)),
                               keyEquivalent: "E")
        item3.image = self.icon
        menu.addItem(item3)

        return menu
    }

    func preparePayload(_ dictionary: Dictionary<String, String>) -> Data? {
        // Serialize a Dictionary into Data to send through the socket
        do {
            let payload = try JSONSerialization.data(withJSONObject: dictionary)
            //NSLog("preparePayload: \(String(data: payload, encoding: .utf8)!)")
            return payload
        } catch {
            //NSLog("Failed to serialize: \(dictionary)")
            return nil
        }
    }

    func getSyncStatus(target: URL?) {
        // Called by requestBadgeIdentifier to ask Drive for a status
        //NSLog("getSyncStatus: target: \(target!.path)")
        if let payload = preparePayload(["cmd": "get-status", "path": target!.path]) {
            self.socket!.send(content: payload)
        }
    }

    func triggerWatch() {
        // Called on startup to ask Drive for the folders to watch
        //NSLog("triggerWatch")
        if let payload = preparePayload(["cmd": "trigger-watch"]) {
            self.socket!.send(content: payload)
        }
    }

    @IBAction func accessOnline(_ sender: AnyObject?) {
        // Event fired by "Access online" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            //NSLog("accessOnline: target: \(item.path)")
            openNXUrl(command: "access-online", target: item)
        }
    }

    @IBAction func copyShareLink(_ sender: AnyObject?) {
        // Event fired by "Copy share-link" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            //NSLog("copyShareLink: target: \(item.path)")
            openNXUrl(command: "copy-share-link", target: item)
        }
    }

    @IBAction func editMetadata(_ sender: AnyObject?) {
        // Event fired by "Edit metadata" menu entry
        let items = FIFinderSyncController.default().selectedItemURLs()
        for item in items! {
            //NSLog("editMetadata: target: \(item.path)")
            openNXUrl(command: "edit-metadata", target: item)
        }
    }

    func openNXUrl(command: String, target: URL?) {
        // Protocol URL "nxdrive://" trigger
        guard let targetPath = target?.path else {
            return
        }
        //NSLog("Target path is \(targetPath)")
        let request = String(format: "nxdrive://%@/%@",
                             command,
                             targetPath.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)!)
        let url = URL(string: request)
        //NSLog("Launching URL \(request)")
        NSWorkspace.shared.open(url!)
    }

}
