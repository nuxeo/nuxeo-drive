//
//  FileState.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 26/03/2018.
//  Copyright © 2018 Nuxeo. All rights reserved.
//

import Foundation
import SQLite3

enum SQLiteError: Error {
    case openDatabase
    case closeDatabase
    case dropTable
    case createTable
    case prepareStatement
    case bindParameter(param: String)
    case finalizeStatement
    case insertEntry
}

class FileStatus {
    internal let dropStatement = "DROP TABLE Status"
    internal let createStatement = "CREATE TABLE Status (path text primary key, status text)"
    internal let insertStatement = "INSERT OR REPLACE INTO Status (path, status) VALUES (?, ?)"
    internal let selectStatement = "SELECT * FROM Status WHERE path = ?"
    internal let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
    var db: OpaquePointer?
    var statement: OpaquePointer?

    init() {
        do {
            try run(sqlite3_open(":memory:", &db), error: SQLiteError.openDatabase)
            try run(sqlite3_exec(db, createStatement, nil, nil, nil), error: SQLiteError.createTable)
        } catch {
            
        }
    }
    
    deinit {
        do {
            try run(sqlite3_exec(db, dropStatement, nil, nil, nil), error: SQLiteError.dropTable)
            statement = nil
            try run(sqlite3_close(db), error: SQLiteError.closeDatabase)
            db = nil
        } catch {
            
        }
    }


    func insertStatus(_ status: String, for path: String) {
        do {
            try run(sqlite3_prepare_v2(db, insertStatement, -1, &statement, nil),
                    error: SQLiteError.prepareStatement)

            try run(sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "path"))
            try run(sqlite3_bind_text(statement, 2, status, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "status"))

            try run(sqlite3_step(statement), error: SQLiteError.insertEntry)
            try run(sqlite3_finalize(statement), error: SQLiteError.finalizeStatement)
        } catch {
            
        }
    }

    func getStatus(for path: String) -> String? {
        do {
            try run(sqlite3_prepare_v2(db, selectStatement, -1, &statement, nil),
                    error: SQLiteError.prepareStatement)
            try run(sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "path"))

            var results: Set<String> = []
            while sqlite3_step(statement) == SQLITE_ROW {
                if let cString = sqlite3_column_text(statement, 1) {
                    results.insert(String(cString: cString))
                }
            }
            try run(sqlite3_finalize(statement), error: SQLiteError.finalizeStatement)

            return results.first
        } catch {
            return nil
        }
    }
    
    func run(_ returnVal: Int32, error: SQLiteError) throws {
        if !(returnVal == SQLITE_OK || returnVal == SQLITE_DONE) {
            let errmsg = String(cString: sqlite3_errmsg(db)!)
            NSLog("\(error): \(errmsg)")
            throw error
        }
    }
}
