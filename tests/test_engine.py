"""Testes com o motor de verdade. Usa engine.path do config.toml ou a variável STOCKFISH_PATH."""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_config
from app.controller import GameController


def _cfg(tmp_path):
    cfg = load_config()
    if os.environ.get("STOCKFISH_PATH"):
        cfg.engine.path = os.environ["STOCKFISH_PATH"]
    if not cfg.resolve(cfg.engine.path).is_file():
        pytest.skip("motor não encontrado (configure engine.path ou STOCKFISH_PATH)")
    cfg.engine.threads = 1
    cfg.engine.hash_mb = 64
    cfg.saves_dir = str(tmp_path)
    cfg.book.enabled = False
    cfg.clock.entry_lag_s = cfg.clock.exec_lag_s = 0.1
    cfg.clock.min_think_s = 0.3
    cfg.clock.max_think_s = 0.5
    return cfg


def _wait(ctrl, phase, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if ctrl.phase == phase:
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def ctrl(tmp_path):
    c = GameController(_cfg(tmp_path))
    c.start()
    yield c
    c.shutdown()


def test_plays_and_ponders(ctrl):
    ctrl.new_game("black")
    assert _wait(ctrl, "aguardando")
    ok, _ = ctrl.opponent_move("e2e4")
    assert ok and _wait(ctrl, "aguardando")
    assert ctrl.last_move["source"] in ("motor", "ponder")
    assert len(ctrl.board.move_stack) == 2


def test_recovers_when_engine_dies_mid_search(ctrl):
    ctrl.cfg.clock.min_think_s = ctrl.cfg.clock.max_think_s = 2.0
    ctrl.new_game("black")
    assert _wait(ctrl, "aguardando")
    ctrl.opponent_move("d2d4")
    time.sleep(0.5)
    ctrl.engine.engine.proc.kill()
    assert _wait(ctrl, "aguardando", 30)
    assert ctrl.engine.restarts >= 1
    assert ctrl.last_move is not None


def test_undo_and_resume(ctrl, tmp_path):
    ctrl.new_game("black")
    assert _wait(ctrl, "aguardando")
    ctrl.opponent_move("e2e4")
    assert _wait(ctrl, "aguardando")
    ok, _ = ctrl.undo_opponent()
    assert ok and len(ctrl.board.move_stack) == 0
    ctrl.opponent_move("d2d4")
    assert _wait(ctrl, "aguardando")
    moves = [m.uci() for m in ctrl.board.move_stack]
    ok, _ = ctrl.resume()
    assert ok
    assert [m.uci() for m in ctrl.board.move_stack] == moves
