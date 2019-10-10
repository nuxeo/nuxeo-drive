//
//  FileState.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 26/03/2018.
//
//  Contributors:
//      Mickaël Schoentgen
//
//  Copyright © 2018-2019 Nuxeo. All rights reserved.
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
    case deleteEntry
}

class FileStatus {
    internal let dropStatusStatement = "DROP TABLE Status"
    internal let createStatusStatement = "CREATE TABLE Status (path text primary key, status text)"
    internal let insertStatusStatement = "INSERT OR REPLACE INTO Status (path, status) VALUES (?, ?)"
    internal let selectStatusStatement = "SELECT * FROM Status WHERE path = ?"
    internal let dropVisitedStatement = "DROP TABLE Visited"
    internal let createVisitedStatement = "CREATE TABLE Visited (path text primary key, last_visit integer)"
    internal let insertVisitedStatement = "INSERT OR REPLACE INTO Visited (path, last_visit) VALUES (?, datetime('now'))"
    internal let selectVisitedStatement = "SELECT * FROM Visited WHERE path = ? AND last_visit + 3600 > datetime('now')"
    internal let deleteVisitedStatement = "DELETE FROM Visited WHERE path = ?"
    internal let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
    var db: OpaquePointer?
    var statement: OpaquePointer?
    let lock = DispatchSemaphore(value: 1)

    init() {
        do {
            lock.wait()
            try run(sqlite3_open(":memory:", &db), error: SQLiteError.openDatabase)
            try run(sqlite3_exec(db, createStatusStatement, nil, nil, nil), error: SQLiteError.createTable)
            try run(sqlite3_exec(db, createVisitedStatement, nil, nil, nil), error: SQLiteError.createTable)
            lock.signal()
        } catch {

        }
    }

    deinit {
        do {
            lock.wait()
            try run(sqlite3_exec(db, dropStatusStatement, nil, nil, nil), error: SQLiteError.dropTable)
            try run(sqlite3_exec(db, dropVisitedStatement, nil, nil, nil), error: SQLiteError.dropTable)
            statement = nil
            try run(sqlite3_close(db), error: SQLiteError.closeDatabase)
            db = nil
            lock.signal()
        } catch {

        }
    }


    func insertStatus(_ status: String, for path: String) {
        do {
            lock.wait()
            try run(sqlite3_prepare_v2(db, insertStatusStatement, -1, &statement, nil),
                    error: SQLiteError.prepareStatement)

            try run(sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "path"))
            try run(sqlite3_bind_text(statement, 2, status, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "status"))

            try run(sqlite3_step(statement), error: SQLiteError.insertEntry)
            try run(sqlite3_finalize(statement), error: SQLiteError.finalizeStatement)
            lock.signal()
        } catch {

        }
    }

    func getStatus(for path: String) -> String? {
        do {
            lock.wait()
            try run(sqlite3_prepare_v2(db, selectStatusStatement, -1, &statement, nil),
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
            lock.signal()

            return results.first
        } catch {
            return nil
        }
    }

    func visit(_ path: String) {
        do {
            lock.wait()
            try run(sqlite3_prepare_v2(db, insertVisitedStatement, -1, &statement, nil),
                    error: SQLiteError.prepareStatement)

            try run(sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "path"))

            try run(sqlite3_step(statement), error: SQLiteError.insertEntry)
            try run(sqlite3_finalize(statement), error: SQLiteError.finalizeStatement)
            lock.signal()
        } catch {

        }
    }

    func removeVisit(_ path: String) {
        do {
            lock.wait()
            try run(sqlite3_prepare_v2(db, deleteVisitedStatement, -1, &statement, nil),
                    error: SQLiteError.prepareStatement)

            try run(sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "path"))

            try run(sqlite3_step(statement), error: SQLiteError.deleteEntry)
            try run(sqlite3_finalize(statement), error: SQLiteError.finalizeStatement)
            lock.signal()
        } catch {

        }
    }

    func shouldVisit(_ path: String) -> Bool {
        var visited = false
        do {
            lock.wait()
            try run(sqlite3_prepare_v2(db, selectVisitedStatement, -1, &statement, nil),
                    error: SQLiteError.prepareStatement)
            try run(sqlite3_bind_text(statement, 1, path, -1, SQLITE_TRANSIENT),
                    error: SQLiteError.bindParameter(param: "path"))

            while sqlite3_step(statement) == SQLITE_ROW {
                if sqlite3_column_text(statement, 1) != nil {
                    visited = true
                }
            }
            try run(sqlite3_finalize(statement), error: SQLiteError.finalizeStatement)
            lock.signal()
        } catch {

        }
        return !visited
    }

    func run(_ returnVal: Int32, error: SQLiteError) throws {
        if !(returnVal == SQLITE_OK || returnVal == SQLITE_DONE) {
            //let errmsg = String(cString: sqlite3_errmsg(db)!)
            //NSLog("\(error): \(errmsg)")
            throw error
        }
    }
}
