"""Simulação de partidas completas: nosso sistema (controlador inteiro) contra um motor.

Serve para três coisas antes do torneio:
  1. provar que não perdemos por tempo com a gestão de relógio e os atrasos humanos;
  2. calibrar a classificação do adversário (forte / médio / fraco);
  3. gerar evidência de testes para a validação do código.

O atraso humano é simulado com pausas reais (o controlador mede tempo de verdade).
O adversário roda em outro processo. Num computador só, o nosso ponder disputa CPU
com o adversário; use --no-ponder para uma comparação justa de força.

Exemplos:
    python tools/simulate.py --opponent fraco --games 2 --minutes 3
    python tools/simulate.py --opponent forte --games 4 --minutes 5 --lag 0.5
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chess  # noqa: E402

from app.config import load_config  # noqa: E402
from app.controller import GameController  # noqa: E402
from app.uci import UciEngine  # noqa: E402

LEVELS = {
    # nome: (Skill Level, divisor do relógio para o tempo por lance)
    "forte": (20, 40),
    "medio": (10, 60),
    "fraco": (2, 80),
}


def wait_phase_change(ctrl: GameController, from_phase: str, timeout: float) -> str:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if ctrl.phase != from_phase:
            return ctrl.phase
        time.sleep(0.01)
    return ctrl.phase


def play_game(args, cfg, opp_path: str, our_white: bool) -> dict:
    ctrl = GameController(cfg)
    ctrl.start()
    skill, divisor = LEVELS[args.opponent]
    opp = UciEngine(opp_path, {"Threads": args.threads, "Hash": 64, "Skill Level": skill, "UCI_ShowWDL": True})
    opp.start()

    color = "white" if our_white else "black"
    ctrl.new_game(color, minutes=args.minutes)
    true_ours = true_theirs = args.minutes * 60.0
    lag_in, lag_out = cfg.clock.entry_lag_s, cfg.clock.exec_lag_s
    our_color = chess.WHITE if our_white else chess.BLACK
    result, reason = None, ""
    max_err = 0.0
    turn_started = time.monotonic()

    try:
        while True:
            with ctrl.lock:
                phase = ctrl.phase
                board = ctrl.board.copy()
            if phase == "fim":
                result, reason = ctrl.result, ctrl.result_reason
                break
            if board.ply() >= args.max_plies:
                result, reason = "1/2-1/2", "limite de lances da simulação"
                break

            if board.turn == our_color:
                # nosso lance: o controlador pensa; o relógio corre desde o fim do lance dele
                phase = wait_phase_change(ctrl, "pensando", 120)
                if ctrl.draw_claim and phase == "aguardando":
                    result, reason = "1/2-1/2", "empate reivindicado pelo nosso sistema"
                    break
                time.sleep(lag_out)  # executor move a peça e aperta o relógio
                true_ours -= time.monotonic() - turn_started
                turn_started = time.monotonic()
                if true_ours <= 0:
                    result, reason = ("0-1" if our_white else "1-0"), "NÓS perdemos no tempo"
                    break
            else:
                fen = board.root().fen()
                moves = [m.uci() for m in board.move_stack]
                think = max(0.05, min(5.0, true_theirs / divisor))
                time.sleep(args.opp_lag)  # operador deles registra o nosso lance
                search = opp.go(fen, moves, movetime=think)
                res = opp.wait(search, think + 10)
                time.sleep(args.opp_lag)  # executor deles move a peça e aperta o relógio
                time.sleep(lag_in)  # nosso operador digita o lance dele
                true_theirs -= (time.monotonic() - turn_started) - lag_in
                turn_started = time.monotonic() - lag_in
                if true_theirs <= 0:
                    result, reason = ("1-0" if our_white else "0-1"), "adversário perdeu no tempo"
                    break
                ok, msg = ctrl.opponent_move(res.bestmove)
                if not ok:
                    result, reason = "?", f"erro ao registrar lance: {msg}"
                    break
                est_ours, est_theirs = ctrl.clock.live()
                max_err = max(max_err, abs(est_ours - true_ours), abs(est_theirs - true_theirs))
    finally:
        state = ctrl.state()
        ctrl.shutdown()
        opp.quit()

    ours_won = (result == "1-0" and our_white) or (result == "0-1" and not our_white)
    return {
        "color": color,
        "result": result,
        "score": 1.0 if ours_won else 0.5 if result == "1/2-1/2" else 0.0,
        "reason": reason,
        "plies": len(state["moves"]),
        "true_ours": true_ours,
        "true_theirs": true_theirs,
        "clock_error": max_err,
        "profile": state["opponent"],
        "modes": state["modes"],
        "stats": state["stats"],
        "restarts": state["engine"]["restarts"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--opponent", choices=list(LEVELS), default="medio")
    ap.add_argument("--opponent-engine", default=None, help="motor adversário (padrão: o mesmo do config)")
    ap.add_argument("--games", type=int, default=2)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--lag", type=float, default=0.3, help="nosso atraso humano simulado em cada ponta (s)")
    ap.add_argument("--opp-lag", type=float, default=None, help="atraso humano do adversário (padrão: igual ao nosso)")
    ap.add_argument("--threads", type=int, default=1, help="threads de cada motor")
    ap.add_argument("--hash", type=int, default=256)
    ap.add_argument("--max-plies", type=int, default=300)
    ap.add_argument("--no-ponder", action="store_true")
    ap.add_argument("--no-book", action="store_true")
    args = ap.parse_args()

    if args.opp_lag is None:
        args.opp_lag = args.lag
    cfg = load_config(args.config)
    cfg.engine.threads = args.threads
    cfg.engine.hash_mb = args.hash
    cfg.engine.ponder = not args.no_ponder
    cfg.book.enabled = not args.no_book
    cfg.clock.minutes = args.minutes
    cfg.clock.entry_lag_s = cfg.clock.exec_lag_s = args.lag
    # relógio curto: reserva e teto proporcionais
    scale = args.minutes / 25.0
    cfg.clock.reserve_s = max(5.0, cfg.clock.reserve_s * scale)
    cfg.clock.max_think_s = max(0.5, cfg.clock.max_think_s * scale)
    cfg.clock.panic_s = max(15.0, cfg.clock.panic_s * scale)
    cfg.clock.critical_s = max(5.0, cfg.clock.critical_s * scale)
    cfg.saves_dir = tempfile.mkdtemp(prefix="cc-sim-")
    opp_path = args.opponent_engine or str(cfg.resolve(cfg.engine.path))

    results = []
    for i in range(args.games):
        r = play_game(args, cfg, opp_path, our_white=(i % 2 == 0))
        results.append(r)
        p = r["profile"]
        print(
            f"Partida {i + 1}: nós de {r['color']:5s} -> {r['result']} ({r['reason']}), {r['plies']} meios-lances | "
            f"relógio real nós {r['true_ours']:.0f}s, adv {r['true_theirs']:.0f}s | erro da estimativa {r['clock_error']:.1f}s | "
            f"perfil detectado: {p['profile']} (precisão {p['accuracy']}%, previsão {p['hit_rate']}%, erros {p['blunders']}) | "
            f"modos {r['modes']} | reinícios {r['restarts']}",
            flush=True,
        )
    total = sum(r["score"] for r in results)
    flags = sum(1 for r in results if "NÓS perdemos no tempo" in r["reason"])
    print(f"\nPlacar: {total}/{len(results)} | derrotas por tempo: {flags}")
    return 0 if flags == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
