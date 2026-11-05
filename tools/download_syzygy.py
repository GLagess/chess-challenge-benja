"""Baixa as tablebases Syzygy de 3, 4 e 5 peças (cerca de 1 GB, 290 arquivos).

Rodar ANTES do torneio, com internet. Retomável: arquivos já baixados são pulados.

    python tools/download_syzygy.py
"""
from __future__ import annotations

import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config  # noqa: E402

BASE = "https://tablebase.lichess.ovh/tables/standard/"
FOLDERS = ["3-4-5-wdl/", "3-4-5-dtz/"]


def fetch(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.read()
        except Exception as exc:
            if attempt == retries - 1:
                raise
            print(f"  nova tentativa ({exc})")
            time.sleep(2)
    raise RuntimeError("inalcançável")


def main() -> int:
    cfg = load_config()
    dest = cfg.resolve(cfg.engine.syzygy_path)
    dest.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    for folder in FOLDERS:
        index = fetch(BASE + folder).decode("utf-8", "replace")
        names = sorted(set(re.findall(r'href="([A-Za-z]+v[A-Za-z]+\.rtb[wz])"', index)))
        files += [folder + n for n in names]
    print(f"{len(files)} arquivos para {dest}")
    done = 0
    for i, rel in enumerate(files, 1):
        name = rel.split("/")[-1]
        target = dest / name
        if target.is_file() and target.stat().st_size > 0:
            continue
        data = fetch(BASE + rel)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
        done += 1
        print(f"  [{i}/{len(files)}] {name} ({len(data) / 1e6:.1f} MB)")
    print(f"Pronto: {done} arquivos novos. Confira com: python tools/check_setup.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
