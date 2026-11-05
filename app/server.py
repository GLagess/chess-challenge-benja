"""Servidor local da interface (só biblioteca padrão; escuta apenas em 127.0.0.1)."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .controller import GameController

STATIC = Path(__file__).resolve().parent / "static"


def make_handler(ctrl: GameController):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ChessChallenge/1.0"

        def log_message(self, fmt, *args):  # silencia o log de cada requisição
            pass

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = (STATIC / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/api/state"):
                self._json(ctrl.state())
            else:
                self._json({"ok": False, "msg": "não encontrado"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                data = {}
            action = self.path.removeprefix("/api/")
            if action == "preview":
                self._json(ctrl.preview(str(data.get("move", ""))))
                return
            try:
                if action == "new_game":
                    ok, msg = ctrl.new_game(data.get("color", "white"), float(data.get("minutes") or 0) or None,
                                            (data.get("fen") or "").strip() or None)
                elif action == "opponent_move":
                    ok, msg = ctrl.opponent_move(str(data.get("move", "")))
                elif action == "undo":
                    ok, msg = ctrl.undo_opponent()
                elif action == "play_now":
                    ok, msg = ctrl.play_now()
                elif action == "sync_clock":
                    ok, msg = ctrl.sync_clocks(str(data.get("ours", "")), str(data.get("theirs", "")))
                elif action == "draw_offer":
                    ok, msg = ctrl.draw_offer()
                elif action == "finish":
                    ok, msg = ctrl.finish(str(data.get("result", "")), str(data.get("reason", "")))
                elif action == "resume":
                    ok, msg = ctrl.resume()
                else:
                    self._json({"ok": False, "msg": "ação desconhecida"}, 404)
                    return
            except Exception as exc:  # a interface nunca derruba o servidor
                ok, msg = False, f"Erro: {exc}"
            self._json({"ok": ok, "msg": msg, "state": ctrl.state()})

    return Handler


def serve(ctrl: GameController, host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(ctrl))
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    return httpd
