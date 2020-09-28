import logging

import SimpleHTTPServer
import SocketServer

PORT = 1999


class BlockingGetHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def end_headers(self):
        for header in self.headers.keys():
            self.send_header(header, self.headers[header])

        SimpleHTTPServer.SimpleHTTPRequestHandler.end_headers(self)

    def do_GET(self):
        logging.warning(self.headers)
        if "x-mode" not in self.headers.keys():
            self.send_response(500)
        else:
            SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)


httpd = SocketServer.TCPServer(("0.0.0.0", PORT), BlockingGetHandler)

httpd.serve_forever()
