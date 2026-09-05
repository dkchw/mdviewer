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
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
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
                    
            elif parsed.path == '/api/search':
                query_args = urllib.parse.parse_qs(parsed.query)
                q = query_args.get('q', [''])[0].lower()
                if not q:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'[]')
                    return
                    
                results = []
                # Walk the directory
                for root, dirs, files in os.walk(directory):
                    # Skip hidden dirs and node_modules
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in ('node_modules', '.obsidian', '.vscode', '.idea')]
                    for file in files:
                        if file.lower().endswith(('.md', '.markdown', '.txt')) and not file.startswith('.'):
                            filepath = os.path.join(root, file)
                            rel_path = os.path.relpath(filepath, directory)
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    lines = f.readlines()
                                    for i, line in enumerate(lines):
                                        if q in line.lower():
                                            results.append({
                                                "file": rel_path,
                                                "line": i,
                                                "text": line.strip()[:200]  # snippet
                                            })
                                            if len(results) > 100:  # cap results for performance
                                                break
                            except Exception:
                                pass
                            if len(results) > 100:
                                break
                    if len(results) > 100:
                        break

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(results).encode('utf-8'))
            elif parsed.path == '/api/config':
                config_file = os.path.expanduser("~/.mdviewer_config.json")
                config_data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r') as f:
                            config_data = json.load(f)
                    except:
                        pass
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(config_data).encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/api/config':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                try:
                    new_patch = json.loads(post_data)
                    config_file = os.path.expanduser("~/.mdviewer_config.json")
                    config_data = {}
                    if os.path.exists(config_file):
                        try:
                            with open(config_file, 'r') as f:
                                config_data = json.load(f)
                        except:
                            pass
                    
                    config_data.update(new_patch)
                    
                    with open(config_file, 'w') as f:
                        json.dump(config_data, f)
                    
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass # Suppress logging

    class ReusableTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    port = 2024
    try:
        httpd = ReusableTCPServer(("127.0.0.1", port), Handler)
    except OSError:
        httpd = ReusableTCPServer(("127.0.0.1", 0), Handler)

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
