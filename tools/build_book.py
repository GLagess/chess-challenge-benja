"""Gera o livro de aberturas da equipe usando o Stockfish 19 em análise longa.

Ideia: nas partidas, cada lance de abertura sai instantâneo (economiza relógio) e com
qualidade de uma análise de dezenas de segundos. Para as posições em que é a nossa vez,
guardamos o melhor lance; para as posições do adversário, ramificamos nas N respostas
mais fortes (MultiPV) — é o que um adversário com motor tende a jogar.

Retomável: pode interromper com Ctrl+C e rodar de novo; o que já foi analisado é mantido.

Exemplo (uma noite de análise):
    python tools/build_book.py --plies 12 --our-time 30 --their-time 8 --branch 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chess  # noqa: E402

from app.book import book_key  # noqa: E402
from app.config import load_config  # noqa: E402
from app.uci import EngineError, UciEngine  # noqa: E402

FIRST_MOVES = ["e2e4", "d2d4", "c2c4", "g1f3"]  # garantimos respostas para as aberturas mais comuns


def load_book(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"format": "cc-book-1", "positions": {}, "replies": {}}


def save_book(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _line(board: chess.Board) -> tuple[str, list[str]]:
    """FEN inicial + lances. O Stockfish 19 recusa FEN com en passant ilegal e morre."""
    root = board.root()
    moves = [m.uci() for m in board.move_stack]
    check = root.copy(stack=False)
    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in check.legal_moves:
            raise EngineError(f"linha inválida para o motor: {uci} em {check.fen()}")
        check.push(move)
    return root.fen(), moves


def analyse(eng: UciEngine, board: chess.Board, seconds: float, multipv: int):
    fen, moves = _line(board)
    last: EngineError | None = None
    for attempt in range(3):
        try:
            if not eng.is_alive():
                eng.restart()
            eng.new_game()
            search = eng.go(fen, moves, movetime=seconds, multipv=multipv)
            return eng.wait(search, seconds + 45)
        except EngineError as exc:
            last = exc
            print(f"\n  Motor falhou na tentativa {attempt + 1}/3 ({exc}).", flush=True)
            if attempt == 2:
                break
            try:
                eng.restart()
            except EngineError as restart_exc:
                last = restart_exc
                print(f"  Não consegui religar o motor: {restart_exc}", flush=True)
                time.sleep(1)
    raise EngineError(f"análise falhou após 3 tentativas: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--engine", default=None, help="caminho do motor (padrão: o do config.toml)")
    ap.add_argument("--out", default=None, help="arquivo do livro (padrão: o do config.toml)")
    ap.add_argument("--plies", type=int, default=12, help="profundidade do livro em meios-lances")
    ap.add_argument("--our-time", type=float, default=30.0, help="segundos por posição nossa")
    ap.add_argument("--their-time", type=float, default=8.0, help="segundos por posição do adversário")
    ap.add_argument("--branch", type=int, default=3, help="respostas do adversário consideradas por posição")
    ap.add_argument("--color", choices=["both", "white", "black"], default="both")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--hash", type=int, default=0, help="MB de hash (0 = automático)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    engine_path = args.engine or str(cfg.resolve(cfg.engine.path))
    out = Path(args.out) if args.out else cfg.resolve(cfg.book.path)
    threads = args.threads or cfg.engine.resolved_threads()

    hash_mb = args.hash or cfg.engine.resolved_hash()
    opts = {"Threads": threads, "Hash": hash_mb, "UCI_ShowWDL": True}
    eng = UciEngine(engine_path, opts)
    eng.start()
    print(f"Motor: {eng.name} | threads {threads} | hash {hash_mb} MB | livro: {out}")

    data = load_book(out)
    data["engine"] = eng.name
    positions: dict = data.setdefault("positions", {})
    replies: dict = data.setdefault("replies", {})
    colors = {"both": [chess.WHITE, chess.BLACK], "white": [chess.WHITE], "black": [chess.BLACK]}[args.color]

    started = time.monotonic()
    analysed = 0
    try:
        for color in colors:
            name = "brancas" if color == chess.WHITE else "pretas"
            print(f"\n=== Livro para quando jogamos de {name} ===")
            frontier = deque([chess.Board()])
            seen: set[str] = set()
            while frontier:
                board = frontier.popleft()
                if board.ply() >= args.plies or board.is_game_over():
                    continue
                key = book_key(board)
                if key in seen:
                    continue
                seen.add(key)

                if board.turn == color:
                    entry = positions.get(key)
                    if not entry or entry.get("time", 0) < args.our_time:
                        res = analyse(eng, board, args.our_time, 1)
                        line = res.lines.get(1)
                        entry = {
                            "move": res.bestmove,
                            "cp": line.cp if line and line.cp is not None else (10000 if line and line.mate and line.mate > 0 else -10000 if line and line.mate else 0),
                            "depth": line.depth if line else 0,
                            "time": args.our_time,
                        }
                        positions[key] = entry
                        analysed += 1
                        save_book(out, data)
                        print(f"  [{board.ply():2d}] nosso: {board.san(chess.Move.from_uci(entry['move']))}"
                              f"  ({entry['cp']:+d} cp, prof. {entry['depth']})  {board.fen()[:50]}")
                    child = board.copy()
                    child.push_uci(entry["move"])
                    frontier.append(child)
                else:
                    cached = replies.get(key)
                    if not cached or cached.get("time", 0) < args.their_time or len(cached["moves"]) < args.branch:
                        res = analyse(eng, board, args.their_time, args.branch)
                        mvs = [ln.pv[0] for _, ln in sorted(res.lines.items()) if ln.pv]
                        cached = {"moves": mvs[: args.branch], "time": args.their_time}
                        replies[key] = cached
                        analysed += 1
                        save_book(out, data)
                    mvs = list(cached["moves"])
                    if board.ply() == 0:
                        mvs += [m for m in FIRST_MOVES if m not in mvs]
                    for uci in mvs:
                        child = board.copy()
                        child.push_uci(uci)
                        frontier.append(child)
                elapsed = time.monotonic() - started
                print(f"    fila {len(frontier):4d} | posições nossas {len(positions)} | {elapsed / 60:.1f} min", end="\r")
    except KeyboardInterrupt:
        print("\nInterrompido. O que já foi analisado está salvo; rode de novo para continuar.")
    except EngineError as exc:
        print(f"\nParei o livro: {exc}")
        print("O que já foi analisado está salvo. Rode o mesmo comando para continuar.")
        return 1
    finally:
        save_book(out, data)
        eng.quit()
    print(f"\nPronto: {len(positions)} posições nossas no livro ({analysed} análises novas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
