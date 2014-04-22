import SimpleHTTPServer
import SocketServer


def run(host='127.0.0.1', port=8000,
        handler=SimpleHTTPServer.SimpleHTTPRequestHandler):

    httpd = SocketServer.TCPServer((host, port), handler)

    print "Serving at port", port
    httpd.serve_forever()

if __name__ == '__main__':
    run()
