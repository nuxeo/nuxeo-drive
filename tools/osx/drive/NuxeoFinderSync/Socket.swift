//
//  SocketCom.swift
//  NuxeoFinderSync
//
//  Created by Léa Klein on 12/04/2018.
//  Copyright © 2018 Nuxeo. All rights reserved.
//

import Foundation

enum SocketError: Error {
    case socketCreation
    case streamInit
}

class Socket {
    let addr: String
    let port: Int
    var outputStream : OutputStream

    init(addr: String, port: Int) throws {
        self.addr = addr
        self.port = port

        var inp: InputStream?
        var out: OutputStream?
        Stream.getStreamsToHost(withName: self.addr,
                                port: self.port,
                                inputStream: &inp,
                                outputStream: &out)

        if out == nil {
            throw SocketError.streamInit
        }

        self.outputStream = out!
        outputStream.open()
        if outputStream.streamError != nil {
            throw SocketError.socketCreation
        }
    }

    deinit {
        outputStream.close()
    }

    func send(_ content: String) {
        let data: Data = content.data(using: String.Encoding.utf8, allowLossyConversion: false)!
        data.withUnsafeBytes {
            outputStream.write($0, maxLength: data.count)
        }
    }
}

class SocketCom {
    let addr: String
    let port: Int

    init(addr: String, port: Int) {
        self.addr = addr
        self.port = port
    }

    func send(content: String) {
        do {
            var socket: Socket? = try Socket(addr: self.addr, port: self.port)
            socket!.send(content)
            socket = nil
        } catch {
            NSLog("Unable to use socket (\(error))")
        }
    }
}
