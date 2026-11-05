"""Inicia o sistema: motor + interface local.

Uso:  python run.py            (abre o navegador em http://127.0.0.1:8765)
      python run.py --no-browser
      python run.py --config outro.toml
"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser

from app.config import load_config
from app.controller import GameController
from app.server import serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Chess Challenge III — sistema da equipe")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    ctrl = GameController(cfg)
    ctrl.start()
    httpd = serve(ctrl, cfg.server.host, cfg.server.port)
    url = f"http://{cfg.server.host}:{cfg.server.port}/"
    print(f"\nInterface: {url}\nCtrl+C para encerrar.\n", flush=True)
    if cfg.server.open_browser and not args.no_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        httpd.shutdown()
        ctrl.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
