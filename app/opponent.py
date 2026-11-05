"""Modelo do adversário: aprende, lance a lance, quão forte ele é.

Tudo é calculado com a nossa própria busca, sem custo extra de CPU:
- perda de expectativa: quanto a nossa expectativa de pontos subiu depois do lance
  dele em relação ao que esperávamos ao jogar o nosso lance (lance perfeito = ~0);
- taxa de acerto da previsão: com que frequência ele jogou o lance que o motor previu
  (motores fortes acertam muito; humanos e programas fracos, pouco);
- tempo médio por lance.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import chess
import chess.engine

from .config import StrategyConfig
from .uci import PvLine


def expectation(line: PvLine, ply: int) -> float:
    """Expectativa de pontos (0..1) do lado que está com a vez na busca."""
    if line.wdl:
        w, d, l = line.wdl
        total = max(1, w + d + l)
        return (w + 0.5 * d) / total
    if line.mate is not None:
        return 1.0 if line.mate > 0 else 0.0
    if line.cp is not None:
        return chess.engine.Cp(line.cp).wdl(model="sf", ply=ply).expectation()
    return 0.5


@dataclass
class MoveRecord:
    loss: float | None = None
    hit: bool | None = None
    seconds: float | None = None


@dataclass
class OpponentModel:
    records: list[MoveRecord] = field(default_factory=list)

    # -- registro (um MoveRecord por lance do adversário) --
    def add(self, hit: bool | None, seconds: float | None) -> MoveRecord:
        rec = MoveRecord(hit=hit, seconds=seconds)
        self.records.append(rec)
        return rec

    def set_loss(self, expected_before: float | None, expected_now: float | None) -> None:
        """Valores na NOSSA perspectiva. Ignora posições já decididas."""
        if not self.records or expected_before is None or expected_now is None:
            return
        if expected_before > 0.97 or expected_before < 0.03:
            return
        self.records[-1].loss = max(0.0, expected_now - expected_before)

    def undo(self) -> None:
        if self.records:
            self.records.pop()

    # -- estatísticas --
    @property
    def losses(self) -> list[float]:
        return [r.loss for r in self.records if r.loss is not None]

    @property
    def samples(self) -> int:
        return len(self.losses)

    @property
    def avg_loss(self) -> float:
        ls = self.losses
        return sum(ls) / len(ls) if ls else 0.0

    def blunders(self, threshold: float) -> int:
        return sum(1 for x in self.losses if x >= threshold)

    @property
    def hit_rate(self) -> float:
        hs = [r.hit for r in self.records if r.hit is not None]
        return sum(hs) / len(hs) if hs else 0.0

    @property
    def predictions(self) -> int:
        return sum(1 for r in self.records if r.hit is not None)

    @property
    def avg_seconds(self) -> float:
        ts = [r.seconds for r in self.records if r.seconds is not None]
        return sum(ts) / len(ts) if ts else 0.0

    @property
    def accuracy(self) -> float:
        """Precisão média por lance (0-100), na mesma escala usada pelo Lichess."""
        ls = self.losses
        if not ls:
            return 0.0
        per_move = [min(100.0, max(0.0, 103.1668 * math.exp(-0.04354 * x * 100) - 3.1669)) for x in ls]
        return sum(per_move) / len(per_move)

    def profile(self, cfg: StrategyConfig) -> str:
        if self.blunders(cfg.blunder_threshold) >= 2:
            return "fraco"  # dois erros graves bastam, mesmo com poucos lances
        if self.samples < cfg.min_samples:
            return "desconhecido"
        if self.avg_loss >= cfg.weak_avg_loss:
            return "fraco"
        if (
            self.hit_rate >= cfg.strong_hit_rate
            and self.avg_loss <= cfg.strong_avg_loss
            and self.blunders(cfg.blunder_threshold) == 0
        ):
            return "forte"
        return "medio"

    def summary(self, cfg: StrategyConfig) -> dict:
        return {
            "profile": self.profile(cfg),
            "samples": self.samples,
            "avg_loss": round(self.avg_loss, 4),
            "accuracy": round(self.accuracy),
            "blunders": self.blunders(cfg.blunder_threshold),
            "hit_rate": round(self.hit_rate * 100),
            "predictions": self.predictions,
            "avg_seconds": round(self.avg_seconds, 1),
        }

    def to_dict(self) -> dict:
        return {"records": [asdict(r) for r in self.records]}

    @classmethod
    def from_dict(cls, data: dict) -> "OpponentModel":
        return cls([MoveRecord(**r) for r in data.get("records", [])])
