"""Livro de aberturas.

Formato principal: JSON próprio gerado por tools/build_book.py (Stockfish 19 com
análise longa). Cada posição guarda um único lance — o melhor encontrado.
Formato opcional: Polyglot (.bin), lido pelo python-chess.
"""
from __future__ import annotations

import json
from pathlib import Path

import chess
import chess.polyglot


def book_key(board: chess.Board) -> str:
    """Chave da posição: peças, vez, roques e en passant legal (sem contadores)."""
    return board.epd(en_passant="legal")


class OpeningBook:
    def __init__(self, json_path: Path | None, polyglot_path: Path | None, max_ply: int = 30):
        self.max_ply = max_ply
        self.positions: dict[str, dict] = {}
        self.polyglot_path = polyglot_path if polyglot_path and polyglot_path.is_file() else None
        self.source = "nenhum"
        if json_path and json_path.is_file():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                self.positions = data.get("positions", {})
                self.source = f"{json_path.name} ({len(self.positions)} posições)"
            except (OSError, ValueError) as exc:
                self.source = f"erro ao ler {json_path.name}: {exc}"
        if self.polyglot_path:
            self.source += f" + {self.polyglot_path.name}"

    def lookup(self, board: chess.Board) -> str | None:
        if board.ply() > self.max_ply:
            return None
        entry = self.positions.get(book_key(board))
        if entry:
            try:
                mv = chess.Move.from_uci(entry["move"])
                if mv in board.legal_moves:
                    return mv.uci()
            except (KeyError, ValueError):
                pass
        if self.polyglot_path:
            try:
                with chess.polyglot.open_reader(self.polyglot_path) as reader:
                    entries = list(reader.find_all(board))
                if entries:
                    best = max(entries, key=lambda e: e.weight)
                    if best.move in board.legal_moves:
                        return best.move.uci()
            except Exception:
                return None
        return None
