//
//  FileState.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 26/03/2018.
//  Copyright © 2018 Nuxeo. All rights reserved.
//

import Foundation
import SQLite3

class FileStatus {
    internal let dropStatement = "DROP TABLE Status"
    internal let createStatement = "CREATE TABLE Status (path text primary key, status text)"
    internal let insertStatement = "INSERT OR REPLACE INTO Status (path, status) VALUES (?, ?)"
    internal let selectStatement = "SELECT * FROM Status WHERE path = ?"
    internal let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
    var db: OpaquePointer?
    var statement: OpaquePointer?

    init() {
        if sqlite3_open(":memory:", &db) != SQLITE_OK {
            NSLog("Error opening database")
        }
        createTable()
    }
    deinit {
        dropTable()
        statement = nil
        if sqlite3_close(db) != SQLITE_OK {
            NSLog("Error closing database")
        }
        db = nil
    }

    func dropTable() {
        if sqlite3_exec(db, dropStatement, nil, nil, nil) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("Error while dropping the Status table: \(errmsg)")
        }
    }

    func createTable() {
        if sqlite3_exec(db, createStatement, nil, nil, nil) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("Error while creating the Status table: \(errmsg)")
        }
    }

    func insert(path: String, status: String) {
        if sqlite3_prepare_v2(db, insertStatement, -1, &statement, nil) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("error preparing insert: \(errmsg)")
        }

        if sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("failure binding path: \(errmsg)")
        }

        if sqlite3_bind_text(statement, 2, status, -1, SQLITE_TRANSIENT) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("failure binding status: \(errmsg)")
        }

        if sqlite3_step(statement) != SQLITE_DONE {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("failure inserting (\(path), \(status)): \(errmsg)")
        }
    }

    func select(path: String) -> Set<String> {
        if sqlite3_prepare_v2(db, selectStatement, -1, &statement, nil) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("error preparing select: \(errmsg)")
        }

        if sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("failure binding path: \(errmsg)")
        }

        var results: Set<String> = []
        while sqlite3_step(statement) == SQLITE_ROW {
            if let cString = sqlite3_column_text(statement, 1) {
                results.insert(String(cString: cString))
            }
        }

        if sqlite3_finalize(statement) != SQLITE_OK {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("error finalizing prepared statement: \(errmsg)")
        }

        return results
    }
}
