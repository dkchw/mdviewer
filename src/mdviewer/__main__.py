import http.server
import socketserver
import json
import os
import urllib.parse
import webbrowser
import threading
import sys
import importlib.resources

def main():
    directory = os.getcwd()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            
            if parsed.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                try:
                    # For Python 3.9+
                    html_content = importlib.resources.files('mdviewer').joinpath('index.html').read_bytes()
                except AttributeError:
                    # For Python 3.8
                    html_content = importlib.resources.read_binary('mdviewer', 'index.html')
                    
                self.wfile.write(html_content)
                
            elif parsed.path in ('/favicon.ico', '/icon.png'):
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.end_headers()
                try:
                    # For Python 3.9+
                    icon_content = importlib.resources.files('mdviewer').joinpath('icon.png').read_bytes()
                except AttributeError:
                    # For Python 3.8
                    icon_content = importlib.resources.read_binary('mdviewer', 'icon.png')
                self.wfile.write(icon_content)
                
            elif parsed.path == '/api/tree':
                query = urllib.parse.parse_qs(parsed.query)
                rel_path = query.get('path', [''])[0]
                
                # Make sure rel_path doesn't escape directory
                target_dir = os.path.abspath(os.path.join(directory, rel_path))
                if not target_dir.startswith(os.path.abspath(directory)):
                    self.send_response(403)
                    self.end_headers()
                    return

                entries = []
                if os.path.isdir(target_dir):
                    try:
                        for entry in os.scandir(target_dir):
                            if entry.name.startswith('.'):
                                continue
                            if entry.is_dir():
                                if entry.name.lower() in ('node_modules', '.obsidian', '.vscode', '.idea'):
                                    continue
                                entries.append({"name": entry.name, "kind": "directory"})
                            elif entry.is_file():
                                if entry.name.lower().endswith(('.md', '.markdown', '.txt')):
                                    entries.append({"name": entry.name, "kind": "file"})
                    except Exception as e:
                        pass
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(entries).encode('utf-8'))
                
            elif parsed.path == '/api/file':
                query = urllib.parse.parse_qs(parsed.query)
                rel_path = query.get('path', [''])[0]
                target_file = os.path.abspath(os.path.join(directory, rel_path))
                
                if not target_file.startswith(os.path.abspath(directory)):
                    self.send_response(403)
                    self.end_headers()
                    return
                    
                try:
                    with open(target_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(content.encode('utf-8'))
                except Exception as e:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass # Suppress logging

    port = 2024
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", port), Handler)
    except OSError:
        httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)

    with httpd:
        port = httpd.server_address[1]
        url = f"http://127.0.0.1:{port}"
        print(f"Serving {directory} at {url}")
        
        # Start browser after a tiny delay to ensure server is fully up
        threading.Timer(0.1, lambda: webbrowser.open(url)).start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down mdviewer.")
            sys.exit(0)

if __name__ == '__main__':
    main()
