"""Último recurso: busca mínima em Python caso o motor falhe repetidamente.

Fraca, mas garante que o sistema SEMPRE devolve um lance legal em poucos décimos de
segundo. Antes dela, o gerenciador do motor já tentou reiniciar e usar o binário reserva.
"""
from __future__ import annotations

import time

import chess

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def _evaluate(board: chess.Board) -> int:
    if board.is_checkmate():
        return -100000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    score = 0
    for piece_type, value in VALUES.items():
        score += value * (len(board.pieces(piece_type, board.turn)) - len(board.pieces(piece_type, not board.turn)))
    score += 2 * board.legal_moves.count()
    return score


def _ordered(board: chess.Board):
    return sorted(board.legal_moves, key=lambda m: (not board.is_capture(m), not board.gives_check(m)))


def _negamax(board: chess.Board, depth: int, alpha: int, beta: int, deadline: float) -> int:
    if depth == 0 or board.is_game_over() or time.monotonic() > deadline:
        return _evaluate(board)
    best = -1_000_000
    for move in _ordered(board):
        board.push(move)
        val = -_negamax(board, depth - 1, -beta, -alpha, deadline)
        board.pop()
        if val > best:
            best = val
        alpha = max(alpha, val)
        if alpha >= beta:
            break
    return best


def emergency_move(board: chess.Board, budget: float = 0.5) -> str:
    deadline = time.monotonic() + budget
    moves = _ordered(board)
    best_move, best_val = moves[0], -1_000_000
    for move in moves:
        board.push(move)
        if board.is_checkmate():
            board.pop()
            return move.uci()
        val = -_negamax(board, 2, -1_000_000, 1_000_000, deadline)
        board.pop()
        if val > best_val:
            best_move, best_val = move, val
        if time.monotonic() > deadline:
            break
    return best_move.uci()
