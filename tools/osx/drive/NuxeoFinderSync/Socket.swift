//
//  SocketCom.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 12/04/2018.
//
//  Contributors:
//      Mickaël Schoentgen
//
//  Copyright © 2018-2019 Nuxeo. All rights reserved.
//
import Foundation

enum SocketError: Error {
    case socketCreation
    case socketConnection
    case streamInit
}

class Socket : NSObject, StreamDelegate {
    let addr: String
    let port: Int
    var inputStream : InputStream?
    var outputStream : OutputStream?
    var connectionTimer : Timer?
    let CONNECTION_TIMEOUT = 5.0

    init(addr: String, port: Int) {
        self.addr = addr
        self.port = port
    }

    deinit {
        self.disconnect()
    }

    func connect() throws {
        Stream.getStreamsToHost(withName: self.addr,
                                port: self.port,
                                inputStream: &self.inputStream,
                                outputStream: &self.outputStream)

        if let instream = self.inputStream, let outstream = self.outputStream {
            instream.delegate = self
            outstream.delegate = self
            instream.schedule(in: .current, forMode: .commonModes)
            outstream.schedule(in: .current, forMode: .commonModes)
            instream.open()
            outstream.open()

            self.connectionTimer = Timer.scheduledTimer(
                timeInterval: self.CONNECTION_TIMEOUT,
                target: self,
                selector: #selector(ensureDiscard),
                userInfo: nil,
                repeats: false
            )
        }
    }

    func disconnect() {
        inputStream?.close()
        outputStream?.close()
    }

    func isInValidState(_ stream: Stream?) -> Bool {
        if stream?.streamStatus == .error {
            return false
        }
        return true
    }

    @objc func ensureDiscard() {
        if !isInValidState(inputStream) || !isInValidState(outputStream) {
            self.disconnect()
        }
        self.connectionTimer?.invalidate()
        self.connectionTimer = nil
    }

    func send(_ content: Data) {
        _ = content.withUnsafeBytes {
            outputStream?.write($0, maxLength: content.count)
        }
    }

    func stream(_ aStream: Stream, handle eventCode: Stream.Event) {
    }
}

class SocketCom {
    let addr: String
    let port: Int

    init(addr: String, port: Int) {
        self.addr = addr
        self.port = port
    }

    func send(content: Data) {
        do {
            var socket: Socket? = Socket(addr: self.addr, port: self.port)
            try socket!.connect()
            socket!.send(content)
            socket = nil
        } catch {
            NSLog("Unable to use socket (\(error))")
        }
    }
}
