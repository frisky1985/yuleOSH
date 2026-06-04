#!/usr/bin/env python3
"""OSH Dashboard Server — lightweight HTTP server for the Web UI."""
import http.server
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

OSH_HOME = os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_DIR = Path(__file__).parent
PORT = int(os.environ.get("OSH_PORT", "8080"))


class OSHHandler(http.server.BaseHTTPRequestHandler):
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == "/" or path == "/index.html":
            self._serve_file(UI_DIR / "dashboard.html", "text/html")
        elif path == "/api/status":
            self._json_response(self._get_status())
        elif path == "/api/evidence":
            self._json_response(self._list_evidence())
        elif path == "/api/reviews":
            self._json_response(self._get_reviews())
        elif path == "/api/ci":
            self._json_response(self._get_ci_results())
        elif path.startswith("/exec"):
            self._handle_exec(parsed.query)
        else:
            self._json_response({"error": "not found"}, 404)
    
    def _serve_file(self, filepath: Path, mime: str):
        if filepath.exists():
            data = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json_response({"error": "file not found"}, 404)
    
    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode())
    
    def _handle_exec(self, query: str):
        params = urllib.parse.parse_qs(query)
        cmd = params.get("cmd", [""])[0]
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60,
                cwd=OSH_HOME,
            )
            output = result.stdout or result.stderr
            self._json_response({
                "status": "ok",
                "exit_code": result.returncode,
                "output": output[:2000],
            })
        except subprocess.TimeoutExpired:
            self._json_response({"status": "error", "output": "Command timed out"}, 500)
        except Exception as e:
            self._json_response({"status": "error", "output": str(e)}, 500)
    
    def _get_status(self) -> dict:
        return {
            "status": "running",
            "osh_home": OSH_HOME,
            "version": "0.1.0",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
    
    def _list_evidence(self) -> dict:
        ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
        files = []
        if ev_dir.exists():
            for f in sorted(ev_dir.iterdir()):
                if f.is_file() and f.name != "compliance-pack.zip":
                    files.append({
                        "name": f.name,
                        "size": f"{f.stat().st_size} B",
                        "mtime": f.stat().st_mtime,
                    })
            zip_file = ev_dir / "compliance-pack.zip"
            if zip_file.exists():
                files.append({
                    "name": "compliance-pack.zip 🎯",
                    "size": f"{zip_file.stat().st_size} B",
                    "mtime": zip_file.stat().st_mtime,
                })
        return {"files": files, "count": len(files)}
    
    def _get_reviews(self) -> dict:
        rev_dir = Path(OSH_HOME) / ".osh" / "reviews"
        sessions = []
        if rev_dir.exists():
            for d in sorted(rev_dir.iterdir()):
                if d.is_dir():
                    sess_file = d / "review-session.json"
                    if sess_file.exists():
                        data = json.loads(sess_file.read_text())
                        sessions.append(data)
        return {"sessions": sessions, "count": len(sessions)}
    
    def _get_ci_results(self) -> dict:
        ci_dir = Path(OSH_HOME) / ".osh" / "ci"
        results = []
        if ci_dir.exists():
            for f in sorted(ci_dir.glob("layer*.json")):
                data = json.loads(f.read_text())
                results.append(data)
        return {"results": results, "count": len(results)}
    
    def log_message(self, format, *args):
        sys.stderr.write(f"[OSH UI] {args[0]}\n")


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), OSHHandler)
    print(f"🌐 OSH Dashboard: http://localhost:{PORT}")
    print(f"   OSH_HOME: {OSH_HOME}")
    print(f"   Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
