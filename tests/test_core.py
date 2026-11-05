"""Testes que não precisam do motor.  Rodar:  python -m pytest -q"""
import json
import sys
from pathlib import Path

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.book import OpeningBook, book_key
from app.clock import GameClock, think_time
from app.config import ClockConfig, StrategyConfig
from app.emergency import emergency_move
from app.notation import describe_move, parse_move, san_pt
from app.opponent import OpponentModel, expectation
from app.strategy import Plan, choose_move, decide_plan
from app.uci import PvLine, parse_info


# ------------------------------------------------------------------ notação
def test_coordinates_and_castling():
    b = chess.Board()
    assert parse_move(b, "e2e4").uci() == "e2e4"
    assert parse_move(b, " E2-E4 ").uci() == "e2e4"
    assert parse_move(b, "g1 f3").uci() == "g1f3"
    b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert parse_move(b, "e1g1").uci() == "e1g1"
    assert parse_move(b, "roque pequeno").uci() == "e1g1"
    assert parse_move(b, "roque grande").uci() == "e1c1"
    with pytest.raises(ValueError, match="pequeno ou grande"):
        parse_move(b, "roque")


def test_words():
    b = chess.Board()
    b.push_uci("e2e4")
    for typed, uci in [("cavalo f6", "g8f6"), ("Cavalo de g8 para f6.", "g8f6"), ("peão e5", "e7e5"),
                       ("Peão de e7 para e5", "e7e5"), ("cavalo g8 f6", "g8f6")]:
        assert parse_move(b, typed).uci() == uci, typed
    b = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/2P5/2N5/PP1PPPPP/R1BQKBNR w KQkq - 0 1")
    assert parse_move(b, "peão captura em d5").uci() == "c4d5"
    assert parse_move(b, "cavalo captura d5").uci() == "c3d5"
    with pytest.raises(ValueError, match="Mais de uma peça"):
        parse_move(b, "captura em d5")


def test_short_notation_is_refused_with_suggestion():
    b = chess.Board()
    b.push_uci("e2e4")
    for typed, hint in [("Cf6", "g8f6"), ("Nf6", "g8f6"), ("e5", "e7e5"), ("E5", "e7e5")]:
        with pytest.raises(ValueError, match=f"Formato não aceito.*{hint}"):
            parse_move(b, typed)
    b = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 6 5")
    with pytest.raises(ValueError, match="e1g1"):
        parse_move(b, "O-O")


def test_illegal_moves_are_explained():
    b = chess.Board()
    with pytest.raises(ValueError, match="pode ir para: e3, e4"):
        parse_move(b, "e2e5")
    with pytest.raises(ValueError, match="Não há peça"):
        parse_move(b, "e4e5")
    with pytest.raises(ValueError, match="é nossa"):
        parse_move(chess.Board("4k3/8/8/8/8/8/4P3/4K3 b - - 0 1"), "e2e3")
    b = chess.Board("4k3/8/8/8/8/2N3N1/8/4K3 w - - 0 1")
    with pytest.raises(ValueError, match="Mais de uma peça"):
        parse_move(b, "cavalo e4")
    assert parse_move(b, "cavalo de c3 para e4").uci() == "c3e4"
    b = chess.Board("4k3/8/8/8/8/8/8/r3K3 w - - 0 1")
    with pytest.raises(ValueError, match="xeque"):
        parse_move(b, "e1f1")


def test_promotion():
    b = chess.Board("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    with pytest.raises(ValueError, match="Promoção"):
        parse_move(b, "e7e8")
    assert parse_move(b, "e7e8d").promotion == chess.QUEEN
    assert parse_move(b, "e7e8c").promotion == chess.KNIGHT
    assert parse_move(b, "e7e8t").promotion == chess.ROOK
    assert parse_move(b, "peão de e7 para e8 promove a dama").promotion == chess.QUEEN
    assert parse_move(b, "peão e8 promove cavalo").promotion == chess.KNIGHT
    with pytest.raises(ValueError, match="Promoção"):
        parse_move(b, "peão e8")


def test_announcement_phrase():
    b = chess.Board()
    assert describe_move(b, chess.Move.from_uci("g1f3"))["say"] == "Cavalo de g1 para f3"
    b = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
    assert describe_move(b, chess.Move.from_uci("e4d5"))["say"] == "Peão de e4 captura em d5"
    b = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    assert describe_move(b, chess.Move.from_uci("a1a8"))["say"] == "Torre de a1 para a8, xeque-mate"
    b = chess.Board("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
    assert describe_move(b, chess.Move.from_uci("e7e8q"))["say"] == "Peão de e7 para e8, promove a dama"


def test_san_pt_and_descriptions():
    assert san_pt("Nf3") == "Cf3"
    assert san_pt("Qxd8+") == "Dxd8+"
    assert san_pt("e8=Q#") == "e8=D#"
    assert san_pt("Rad1") == "Tad1"
    assert san_pt("Kxe2") == "Rxe2"
    b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    d = describe_move(b, chess.Move.from_uci("e1g1"))
    assert "Roque pequeno" in d["text"] and any("h1→f1" in n for n in d["notes"])
    b = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    d = describe_move(b, chess.Move.from_uci("e5d6"))
    assert any("d5" in n for n in d["notes"])


# ------------------------------------------------------------------ UCI
def test_parse_info_line():
    line = ("info depth 17 seldepth 36 multipv 2 score cp -35 lowerbound wdl 5 924 71 nodes 405689 "
            "nps 1014222 hashfull 148 tbhits 3 time 400 pv e7e5 g1f3")
    pl = parse_info(line)
    assert pl.depth == 17 and pl.multipv == 2 and pl.cp == -35 and pl.bound == "lowerbound"
    assert pl.wdl == (5, 924, 71) and pl.tbhits == 3 and pl.pv == ["e7e5", "g1f3"]
    assert parse_info("info depth 20 currmove e2e4 currmovenumber 1") is None
    assert parse_info("info depth 5 score mate 3 pv a1a8").mate == 3


# ------------------------------------------------------------------ relógio
class FakeTime:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_clock_accounting():
    ft = FakeTime()
    cfg = ClockConfig(minutes=25, entry_lag_s=3, exec_lag_s=4)
    c = GameClock(cfg, now=ft)
    c.reset(25)
    c.start(our_turn=False)          # jogamos de pretas
    ft.t = 13                          # ele pensou 10 s, nós digitamos em 3 s
    assert c.opponent_moved() == pytest.approx(10)
    ft.t = 20                          # 7 s pensando após registrar + 3 s de digitação + 4 s de execução
    used = c.we_moved()
    assert used == pytest.approx(3 + 7 + 4)
    ours, theirs = c.live()
    assert theirs == pytest.approx(1500 - 10)
    assert ours == pytest.approx(1500 - 14)


def test_time_management_survives_long_games():
    """Com 7 s de demora humana por lance, chegamos ao lance 120 sem estourar o tempo."""
    cfg = ClockConfig()
    clock = 1500.0
    for move in range(1, 121):
        t = 0.0 if move <= 8 else think_time(cfg, clock, move, 30)
        clock -= t + cfg.entry_lag_s + cfg.exec_lag_s
        assert clock > 0, f"estourou no lance {move}"
    assert think_time(cfg, 1400, 15, 1) < 0.1  # lance único: instantâneo
    assert think_time(cfg, 20, 60, 30) <= 0.1   # relógio crítico


# ------------------------------------------------------------------ adversário
def test_opponent_profiles():
    cfg = StrategyConfig()
    strong = OpponentModel()
    for _ in range(8):
        strong.add(hit=True, seconds=10)
        strong.set_loss(0.5, 0.505)
    assert strong.profile(cfg) == "forte"

    weak = OpponentModel()
    for loss in (0.0, 0.2, 0.01, 0.3):
        weak.add(hit=False, seconds=5)
        weak.set_loss(0.5, 0.5 + loss)
    assert weak.profile(cfg) == "fraco"  # dois erros graves bastam

    unknown = OpponentModel()
    unknown.add(hit=True, seconds=3)
    assert unknown.profile(cfg) == "desconhecido"
    unknown.set_loss(0.99, 0.99)  # posição decidida não conta
    assert unknown.samples == 0


def test_expectation_uses_wdl_then_cp():
    assert expectation(PvLine(wdl=(500, 500, 0)), 20) == pytest.approx(0.75)
    assert expectation(PvLine(mate=2), 20) == 1.0
    assert expectation(PvLine(mate=-2), 20) == 0.0
    assert 0.5 < expectation(PvLine(cp=50), 20) < 0.7


# ------------------------------------------------------------------ estratégia
def test_plan_modes():
    assert decide_plan("forte", 0.5, 1000, 1000).mode == "solido"
    assert decide_plan("fraco", 0.5, 1000, 1000).mode == "antiempate"
    assert decide_plan("forte", 0.9, 1000, 1000).mode == "conversao"
    assert decide_plan("medio", 0.2, 1000, 1000).mode == "complicar"
    assert decide_plan("forte", 0.5, 1000, 300).mode == "pressao"
    assert decide_plan("forte", 0.5, 200, 400).mode == "salvar"
    assert decide_plan("fraco", 0.5, 1000, 1000, adaptive=False).mode == "solido"


def _repetition_board():
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    for u in ["a1a2", "g8h8", "a2a1", "h8g8"]:
        b.push_uci(u)
    return b  # Ta1-a2 de novo repetiria a posição


def test_selector_avoids_repetition_within_margin():
    b = _repetition_board()
    lines = {
        1: PvLine(multipv=1, depth=20, wdl=(300, 600, 100), pv=["a1a2"]),
        2: PvLine(multipv=2, depth=20, wdl=(290, 610, 100), pv=["a1a8"]),
    }
    mv, _, _ = choose_move(b, lines, Plan("antiempate", 3, 0.05, 1.0), "a1a2")
    assert mv == "a1a8"
    mv, _, _ = choose_move(b, lines, Plan("solido", 1, 0.0, 1.0), "a1a2")
    assert mv == "a1a2"


def test_selector_respects_margin():
    b = _repetition_board()
    lines = {
        1: PvLine(multipv=1, depth=20, wdl=(600, 400, 0), pv=["a1a2"]),
        2: PvLine(multipv=2, depth=20, wdl=(100, 700, 200), pv=["a1a8"]),
    }
    mv, _, _ = choose_move(b, lines, Plan("antiempate", 3, 0.05, 1.0), "a1a2")
    assert mv == "a1a2"  # a alternativa é muito pior: fica com o melhor


def test_selector_prefers_repetition_when_saving_clock():
    b = _repetition_board()
    lines = {
        1: PvLine(multipv=1, depth=20, wdl=(0, 1000, 0), pv=["a1a8"]),
        2: PvLine(multipv=2, depth=20, wdl=(0, 990, 10), pv=["a1a2"]),
    }
    mv, _, _ = choose_move(b, lines, Plan("salvar", 2, 0.03, 0.6), "a1a8")
    assert mv == "a1a2"


# ------------------------------------------------------------------ livro e emergência
def test_book_lookup(tmp_path):
    b = chess.Board()
    path = tmp_path / "livro.json"
    path.write_text(json.dumps({"positions": {book_key(b): {"move": "e2e4", "cp": 30}}}))
    book = OpeningBook(path, None, max_ply=30)
    assert book.lookup(b) == "e2e4"
    b.push_uci("d2d4")
    assert book.lookup(b) is None


def test_emergency_move_is_legal_and_finds_mate():
    b = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    assert emergency_move(b, 0.5) == "a1a8"
    b = chess.Board()
    assert chess.Move.from_uci(emergency_move(b, 0.2)) in b.legal_moves
