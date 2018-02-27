//
//  FinderSync.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 20/02/2018.
//  Copyright © 2018 Nuxeo. All rights reserved.
//

import Cocoa
import FinderSync

class FinderSync: FIFinderSync {
    var myFolderURL = URL(fileURLWithPath: "/Users/lea/Nuxeo Drive")
    
    override init() {
        super.init()
        
        NSLog("FinderSync() launched from %@", Bundle.main.bundlePath as NSString)
        
        // Set up the directory we are syncing.
        FIFinderSyncController.default().directoryURLs = [self.myFolderURL]
        
        // Set up images for our badge identifiers. For demonstration purposes, this uses off-the-shelf images.
        //FIFinderSyncController.default().setBadgeImage(NSImage(named: .colorPanel)!, label: "Status One" , forBadgeIdentifier: "One")
        //FIFinderSyncController.default().setBadgeImage(NSImage(named: .caution)!, label: "Status Two", forBadgeIdentifier: "Two")
    }
    
    // MARK: - Primary Finder Sync protocol methods
    
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
        NSLog("requestBadgeIdentifierForURL: %@", url.path as NSString)
        
        // For demonstration purposes, this picks one of our two badges, or no badge at all, based on the filename.
        //let whichBadge = abs(url.path.hash) % 3
        //let badgeIdentifier = ["", "One", "Two"][whichBadge]
        //FIFinderSyncController.default().setBadgeIdentifier(badgeIdentifier, for: url)
    }
    
    // MARK: - Menu and toolbar item support
    
    override var toolbarItemName: String {
        return "FinderSy"
    }
    
    override var toolbarItemToolTip: String {
        return "FinderSy: Click the toolbar item for a menu."
    }
    
    override var toolbarItemImage: NSImage {
        return NSImage.init(byReferencingFile: "nuxeo.iconset/icon_32x32.png")!
    }
    
    override func menu(for menuKind: FIMenuKind) -> NSMenu {
        // Produce a menu for the extension.
        let menu = NSMenu(title: "")
        menu.addItem(withTitle: "Access online", action: #selector(openInBrowser(_:)), keyEquivalent: "")
        menu.addItem(withTitle: "Copy share-link", action: #selector(copyShareLink(_:)), keyEquivalent: "")
        return menu
    }
    
    @IBAction func openInBrowser(_ sender: AnyObject?) {
        let target = FIFinderSyncController.default().targetedURL()
        let item = sender as! NSMenuItem
        NSLog("openInBrowser: menu item: %@, target = %@", item.title as NSString, target!.path as NSString)
        openNXUrl(command: "access", target: target)
    }
    
    @IBAction func copyShareLink(_ sender: AnyObject?) {
        let target = FIFinderSyncController.default().targetedURL()
        let item = sender as! NSMenuItem
        NSLog("copyShareLink: menu item: %@, target = %@", item.title as NSString, target!.path as NSString)
        openNXUrl(command: "share_link", target: target)
    }
    
    func openNXUrl(command: String, target: URL?) {
        guard let targetPath = target?.path else {
            return
        }
        NSLog("Target path is %@", targetPath)
        let request = String(format: "nxdrive://%@/%@", command, targetPath)
        let url = URL(string: request.replacingOccurrences(of: " ", with: "%20"))
        NSLog("Launching url %@", request)
        NSWorkspace.shared.open(url!)
    }
}

