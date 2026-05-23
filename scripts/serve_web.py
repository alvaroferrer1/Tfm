#!/usr/bin/env python3
"""Servidor HTTP con cabeceras no-cache para la app Flutter web."""
import http.server
import sys
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "app" / "build" / "web"
PORT = 3000

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # silencioso

if __name__ == "__main__":
    import os
    os.chdir(WEB_DIR)
    with http.server.HTTPServer(("", PORT), NoCacheHandler) as srv:
        print(f"Servidor web en http://localhost:{PORT}")
        srv.serve_forever()
