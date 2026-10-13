import os
import socket
import http.server
import socketserver
import threading

class SilentHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request logging to keep console clean
        pass

class KetcherServer:
    def __init__(self, directory="ketcher"):
        self.directory = os.path.abspath(directory)
        self.port = self._find_free_port()
        self.httpd = None
        self.thread = None

    def _find_free_port(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('localhost', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def start(self):
        # Change working directory in handler
        directory = self.directory
        
        class CustomHTTPRequestHandler(SilentHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

        handler = CustomHTTPRequestHandler
        self.httpd = socketserver.TCPServer(('localhost', self.port), handler)
        
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        print(f"Ketcher Server läuft lokal auf http://localhost:{self.port}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            print("Ketcher Server gestoppt.")

    def get_url(self):
        return f"http://localhost:{self.port}/index.html"
