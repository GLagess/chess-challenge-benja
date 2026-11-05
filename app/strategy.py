"""Estratégia adaptativa: decide COMO buscar e QUAL lance escolher.

O Stockfish devolve as melhores linhas com a avaliação de cada uma. Esta camada
escolhe entre elas conforme o adversário e a situação da partida:

- sólido: joga o melhor lance do motor (padrão e contra adversários fortes);
- anti-empate: em posição equilibrada contra adversário fraco/médio, aceita um lance
  levemente inferior (dentro de uma margem pequena) se ele evita repetição, trocas
  e simplificação — mais chances para o adversário errar;
- pressão de relógio: o adversário tem bem menos tempo; mantém o jogo vivo para o
  relógio dele correr (margem mínima);
- conversão: já estamos ganhando; joga o melhor lance mais rápido;
- complicar: estamos pior contra adversário falível; busca as linhas mais complexas;
- segurar o relógio: posição igual e NÓS com menos tempo; prefere repetir e simplificar
  para chegar a um empate reivindicável antes de o nosso relógio acabar.

O lance escolhido NUNCA fica fora da margem definida em relação ao melhor lance.
"""
from __future__ import annotations

from dataclasses import dataclass

import chess

from .opponent import expectation
from .uci import PvLine

PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

MODE_LABEL = {
    "solido": "Jogo normal",
    "antiempate": "Evitar empate",
    "pressao": "Apertar o tempo deles",
    "conversao": "Estamos ganhando",
    "complicar": "Complicar o jogo",
    "salvar": "Cuidar do nosso tempo",
}


@dataclass
class Plan:
    mode: str
    multipv: int
    margin: float        # quanto de expectativa aceitamos perder em troca de estilo
    time_factor: float

    @property
    def label(self) -> str:
        return MODE_LABEL.get(self.mode, self.mode)


def decide_plan(
    profile: str,
    expected: float | None,
    our_clock: float,
    their_clock: float,
    adaptive: bool = True,
    panic_s: float = 120.0,
) -> Plan:
    e = 0.5 if expected is None else expected
    if not adaptive:
        return Plan("solido", 1, 0.0, 1.0)

    weak = profile == "fraco"
    medium = profile == "medio"

    if e >= 0.85:
        plan = Plan("conversao", 1, 0.0, 0.5 if weak else 0.7)
    elif e <= 0.25 and (weak or medium):
        plan = Plan("complicar", 4, 0.08 if weak else 0.05, 1.0)
    elif 0.3 <= e <= 0.7 and our_clock < their_clock * 0.9 and our_clock < panic_s * 2.5:
        plan = Plan("salvar", 2, 0.03, 0.6)
    elif 0.35 <= e <= 0.65:
        clock_edge = their_clock < our_clock * 0.8 and their_clock < 600
        if weak:
            plan = Plan("antiempate", 3, 0.05, 0.7)
        elif medium:
            plan = Plan("antiempate", 3, 0.03, 0.9)
        elif clock_edge:
            plan = Plan("pressao", 2, 0.015, 0.9)
        else:
            plan = Plan("solido", 1, 0.0, 1.0)
    else:
        plan = Plan("solido", 1, 0.0, 0.8 if weak else 1.0)

    # estamos atrás no relógio: acelera um pouco
    if our_clock < their_clock * 0.85 and our_clock < 900:
        plan.time_factor *= 0.8
    return plan


def _style_bonus(board: chess.Board, move: chess.Move, mode: str) -> float:
    """Bônus/penalidade de estilo, em unidades de expectativa (pequenos de propósito)."""
    bonus = 0.0
    captured = board.piece_at(move.to_square)
    is_capture = board.is_capture(move)
    resets_fifty = is_capture or board.piece_type_at(move.from_square) == chess.PAWN
    halfmove = board.halfmove_clock

    board.push(move)
    try:
        if mode == "salvar":
            if board.is_repetition(3) or board.is_insufficient_material():
                bonus += 0.05
            elif board.is_repetition(2):
                bonus += 0.03
            if captured is not None and captured.piece_type != chess.PAWN:
                bonus += 0.003 * PIECE_VALUE[captured.piece_type]
            return bonus
        if board.is_repetition(3) or board.is_insufficient_material():
            bonus -= 0.5
        elif board.is_repetition(2):
            bonus -= 0.06
        if mode in ("antiempate", "complicar", "pressao"):
            if captured is not None and captured.piece_type != chess.PAWN:
                bonus -= 0.004 * PIECE_VALUE[captured.piece_type]  # trocas simplificam
            if halfmove >= 70 and not resets_fifty:
                bonus -= 0.02
            mobility = board.legal_moves.count()
            bonus += 0.0004 * min(mobility, 50)
            if board.is_check():
                bonus += 0.003
    finally:
        board.pop()
    return bonus


def choose_move(
    board: chess.Board,
    lines: dict[int, PvLine],
    plan: Plan,
    bestmove: str | None,
) -> tuple[str, PvLine | None, str]:
    """Escolhe o lance. Devolve (uci, linha escolhida, motivo)."""
    best_line = lines.get(1)
    fallback = bestmove or (best_line.pv[0] if best_line and best_line.pv else None)
    if fallback is None:
        raise ValueError("busca sem lance")
    if plan.multipv <= 1 or plan.margin <= 0 or len(lines) <= 1 or best_line is None:
        return fallback, best_line, "melhor lance"

    ply = board.ply()
    best_e = expectation(best_line, ply)
    if best_line.mate is not None and best_line.mate > 0:
        return fallback, best_line, "mate forçado"

    best_choice = (best_e + _style_bonus(board, chess.Move.from_uci(best_line.pv[0]), plan.mode), best_line)
    for idx, line in lines.items():
        if idx == 1 or not line.pv or line.depth < best_line.depth - 3:
            continue
        try:
            mv = chess.Move.from_uci(line.pv[0])
        except ValueError:
            continue
        if mv not in board.legal_moves:
            continue
        e = expectation(line, ply)
        if e < best_e - plan.margin:
            continue
        utility = e + _style_bonus(board, mv, plan.mode)
        if utility > best_choice[0]:
            best_choice = (utility, line)

    chosen = best_choice[1]
    if chosen is best_line:
        return fallback, best_line, "melhor lance"
    return chosen.pv[0], chosen, f"{plan.label.lower()} (alternativa {expectation(chosen, ply):.2f} vs {best_e:.2f})"
