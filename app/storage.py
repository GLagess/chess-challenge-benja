"""Salvamento automático: o estado da partida vai para o disco a cada lance.

Se o programa inteiro fechar (queda de energia, crash, fechamento acidental), basta
abrir de novo e clicar em 'Retomar partida'.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import chess
import chess.pgn


class Storage:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "partidas").mkdir(exist_ok=True)
        self.current = self.folder / "partida_atual.json"

    def save(self, data: dict) -> None:
        tmp = self.current.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.current)  # troca atômica: nunca deixa arquivo pela metade

    def load(self) -> dict | None:
        if not self.current.is_file():
            return None
        try:
            return json.loads(self.current.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def archive_pgn(self, board: chess.Board, our_white: bool, result: str, event_note: str = "") -> Path:
        game = chess.pgn.Game.from_board(board)
        game.headers["Event"] = "Chess Challenge III - iCEV 2026"
        game.headers["Date"] = dt.date.today().strftime("%Y.%m.%d")
        game.headers["White"] = "Nós" if our_white else "Adversário"
        game.headers["Black"] = "Adversário" if our_white else "Nós"
        game.headers["Result"] = result
        if event_note:
            game.headers["Annotator"] = event_note
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.folder / "partidas" / f"{stamp}.pgn"
        path.write_text(str(game) + "\n", encoding="utf-8")
        return path
