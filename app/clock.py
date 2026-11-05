"""Relógio físico e gestão de tempo.

O relógio de verdade fica na mesa; aqui estimamos os dois a partir dos eventos do
sistema (lance do adversário registrado, nosso lance mostrado) mais os atrasos
humanos medidos em treino. O operador pode sincronizar com o relógio real a qualquer
momento.

Sem acréscimo (morte súbita), cada lance custa também o tempo humano de digitar,
mover a peça e apertar o relógio. O cálculo do tempo de pensamento reserva esse
custo para todos os lances que ainda faltam.
"""
from __future__ import annotations

import time
from typing import Callable

from .config import ClockConfig


class GameClock:
    def __init__(self, cfg: ClockConfig, now: Callable[[], float] = time.monotonic):
        self.cfg = cfg
        self.now = now
        self.ours = cfg.minutes * 60.0
        self.theirs = cfg.minutes * 60.0
        self.running: str | None = None  # "ours" | "theirs" | None
        self.turn_started: float = 0.0

    def reset(self, minutes: float) -> None:
        self.ours = self.theirs = minutes * 60.0
        self.running = None

    def start(self, our_turn: bool) -> None:
        self.running = "ours" if our_turn else "theirs"
        self.turn_started = self.now()

    def opponent_moved(self) -> float:
        """Lance do adversário registrado. Devolve o tempo que ele gastou."""
        t = self.now()
        used = max(0.0, t - self.turn_started - self.cfg.entry_lag_s)
        if self.running == "theirs":
            self.theirs -= used
            self.theirs += self.cfg.increment_s
        self.running = "ours"
        # nosso relógio começou a correr quando ele apertou o relógio dele
        self.turn_started = t - self.cfg.entry_lag_s
        return used

    def we_moved(self) -> float:
        """Nosso lance apareceu na tela. Devolve o tempo que gastamos (com execução)."""
        t = self.now()
        used = max(0.0, t - self.turn_started) + self.cfg.exec_lag_s
        if self.running == "ours":
            self.ours -= used
            self.ours += self.cfg.increment_s
        self.running = "theirs"
        # o relógio dele começa quando apertarmos o nosso
        self.turn_started = t + self.cfg.exec_lag_s
        return used

    def live(self) -> tuple[float, float]:
        elapsed = max(0.0, self.now() - self.turn_started)
        ours, theirs = self.ours, self.theirs
        if self.running == "ours":
            ours -= elapsed
        elif self.running == "theirs":
            theirs -= elapsed
        return ours, theirs

    def sync(self, ours: float | None, theirs: float | None) -> None:
        if ours is not None:
            self.ours = ours
        if theirs is not None:
            self.theirs = theirs
        self.turn_started = self.now()

    def stop(self) -> None:
        self.ours, self.theirs = self.live()
        self.running = None

    def to_dict(self) -> dict:
        ours, theirs = self.live()
        return {"ours": ours, "theirs": theirs, "running": self.running}

    def load(self, data: dict) -> None:
        self.ours = float(data.get("ours", self.ours))
        self.theirs = float(data.get("theirs", self.theirs))
        self.running = data.get("running")
        self.turn_started = self.now()


def think_time(
    cfg: ClockConfig,
    our_clock: float,
    fullmove: int,
    legal_count: int,
    factor: float = 1.0,
) -> float:
    """Segundos de busca do motor para este lance."""
    if legal_count <= 1:
        return 0.05
    if our_clock <= cfg.critical_s:
        return 0.1
    if our_clock <= cfg.panic_s:
        return max(0.15, min(1.0, our_clock / 150.0))
    overhead = cfg.entry_lag_s + cfg.exec_lag_s
    moves_to_go = max(cfg.min_moves_to_go, cfg.moves_to_go_base - cfg.moves_to_go_slope * fullmove)
    usable = our_clock - cfg.reserve_s - moves_to_go * overhead
    if usable <= 0:
        return cfg.min_think_s
    t = usable / moves_to_go * factor
    return max(cfg.min_think_s, min(cfg.max_think_s, t))
