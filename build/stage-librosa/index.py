import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from handler import handle

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Handle chunked encoding if present
        if self.headers.get('Transfer-Encoding') == 'chunked':
            post_data = b""
            try:
                while True:
                    line = self.rfile.readline().strip()
                    if not line:
                        break
                    chunk_size = int(line, 16)
                    if chunk_size == 0:
                        self.rfile.readline() # consume final CRLF
                        break
                    post_data += self.rfile.read(chunk_size)
                    self.rfile.readline() # consume trailing CRLF
            except Exception as e:
                sys.stderr.write(f"DEBUG: Chunked read error: {str(e)}\n")
        else:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                 content_length = int(self.headers.get('content-length', 0))
            post_data = self.rfile.read(content_length)
        
        sys.stderr.write(f"DEBUG: Final post data length: {len(post_data)}\n")
        
        event = type('Event', (), {'body': post_data})()
        context = {}
        
        try:
            response_data = handle(event, context)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response_data.encode('utf-8'))
        except Exception as e:
            sys.stderr.write(f"DEBUG: Exception: {str(e)}\n")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

if __name__ == "__main__":
    port = int(os.getenv("port", 5000))
    # Using ThreadingHTTPServer to handle concurrent requests per pod
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    sys.stderr.write(f"Starting threading server on port {port}\n")
    server.serve_forever()
