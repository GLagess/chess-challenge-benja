"""Verificação antes de cada partida (e no ensaio geral).

    python tools/check_setup.py

Confere Python, biblioteca de xadrez, motor, velocidade real do notebook, tablebases,
livro de aberturas, pasta de salvamento e se a internet está desligada.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OK, WARN, FAIL = "OK   ", "AVISO", "FALHA"
problems = 0


def report(status: str, msg: str) -> None:
    global problems
    if status == FAIL:
        problems += 1
    print(f"[{status}] {msg}")


def main() -> int:
    if sys.version_info < (3, 11):
        report(FAIL, f"Python {sys.version.split()[0]}: precisa de 3.11 ou mais novo.")
        return 1
    report(OK, f"Python {sys.version.split()[0]}")

    try:
        import chess
        report(OK, f"python-chess {chess.__version__}")
    except ImportError:
        report(FAIL, "python-chess não instalado: rode  pip install -r requirements.txt")
        return 1

    from app.config import load_config
    from app.engine import EngineManager
    from app.book import OpeningBook

    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    path = cfg.resolve(cfg.engine.path)
    if not path.is_file():
        report(FAIL, f"Motor não encontrado em {path}. Ajuste engine.path no config.toml.")
        return 1
    report(OK, f"Motor em {path}")
    if cfg.engine.fallback_path:
        fb = cfg.resolve(cfg.engine.fallback_path)
        report(OK if fb.is_file() else WARN, f"Motor reserva: {fb}" + ("" if fb.is_file() else " (não encontrado)"))
    else:
        report(WARN, "Sem motor reserva configurado (engine.fallback_path).")

    tb = cfg.resolve(cfg.engine.syzygy_path)
    n_tb = len(list(tb.glob("*.rtbw"))) if tb.is_dir() else 0
    report(OK if n_tb >= 145 else WARN, f"Tablebases Syzygy: {n_tb} arquivos WDL em {tb}"
           + ("" if n_tb >= 145 else " (esperado 145 para 3-4-5 peças; rode tools/download_syzygy.py)"))

    mgr = EngineManager(cfg, log=lambda m: None)
    try:
        mgr.start()
    except Exception as exc:
        report(FAIL, f"Motor não iniciou: {exc}")
        return 1
    eng = mgr.engine
    report(OK, f"{eng.name} iniciado: {cfg.engine.resolved_threads()} threads, hash {cfg.engine.resolved_hash()} MB")
    if eng.tablebase_msg:
        report(OK, eng.tablebase_msg)

    fen = "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N2N2/PP2BPPP/R2QKB1R w KQ - 0 9"
    res = mgr.search(fen, [], 5.0)
    line = res.lines.get(1)
    nps = line.nps if line else 0
    depth = line.depth if line else 0
    status = OK if nps >= 5_000_000 else WARN
    report(status, f"Velocidade: {nps / 1e6:.1f} milhões de nós/s, profundidade {depth} em 5 s"
           + ("" if status == OK else " (baixa: notebook na tomada e em modo de desempenho máximo?)"))
    mgr.shutdown()

    book = OpeningBook(cfg.resolve(cfg.book.path),
                       cfg.resolve(cfg.book.polyglot_path) if cfg.book.polyglot_path else None)
    report(OK if book.positions else WARN, f"Livro de aberturas: {book.source}"
           + ("" if book.positions else " (gere com tools/build_book.py)"))

    saves = cfg.resolve(cfg.saves_dir)
    try:
        saves.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=saves):
            pass
        report(OK, f"Pasta de salvamento gravável: {saves}")
    except OSError as exc:
        report(FAIL, f"Não consigo gravar em {saves}: {exc}")

    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1.5).close()
        report(WARN, "Internet LIGADA. O edital proíbe comunicação externa durante as partidas: ative o modo avião.")
    except OSError:
        report(OK, "Internet desligada.")

    print("\nChecklist manual: notebook na tomada, modo de energia no máximo, suspensão e bloqueio de tela")
    print("desligados, Windows Update pausado, outros programas fechados, base com cooler, relógio sincronizado.")
    print("\nTudo certo." if problems == 0 else f"\n{problems} problema(s) para resolver antes da partida.")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent.parent)
    sys.exit(main())
