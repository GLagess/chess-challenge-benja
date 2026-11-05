"""Controlador da partida.

Toda comunicação com o motor acontece numa única thread de trabalho (fila de jobs),
o que elimina disputas entre comandos UCI. As requisições da interface só alteram o
estado e enfileiram jobs; a única exceção é o comando 'stop', que é atômico.

Fluxo de um lance nosso:
  1. para o ponder e verifica se o adversário jogou o lance previsto;
  2. livro de aberturas -> lance instantâneo;
  3. plano adaptativo (perfil do adversário + avaliação + relógios);
  4. tempo de busca (descontando o ponder em caso de acerto);
  5. busca no Stockfish (MultiPV quando o plano pede) -> atualiza o modelo do adversário;
  6. seletor escolhe o lance -> mostra, salva, começa a pensar no tempo do adversário.
"""
from __future__ import annotations

import collections
import datetime as dt
import queue
import threading
import time
import traceback

import chess

from .book import OpeningBook, book_key
from .clock import GameClock, think_time
from .config import Config
from .emergency import emergency_move
from .engine import EngineManager
from .notation import coord_text, describe_move, parse_move, san_pt
from .opponent import OpponentModel, expectation
from .storage import Storage
from .strategy import MODE_LABEL, Plan, choose_move, decide_plan
from .uci import EngineError, PvLine

COLOR_NAME = {chess.WHITE: "brancas", chess.BLACK: "pretas"}


def _fmt_clock(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 60:02d}:{s % 60:02d}"


def _parse_clock(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    if ":" in text:
        mm, ss = text.split(":", 1)
        return int(mm) * 60 + float(ss)
    return float(text) * 60  # só minutos


class GameController:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.events: collections.deque[str] = collections.deque(maxlen=200)
        self.storage = Storage(cfg.resolve(cfg.saves_dir))
        self.log_file = self.storage.folder / "log.txt"
        self.engine = EngineManager(cfg, self._log)
        self.book = OpeningBook(
            cfg.resolve(cfg.book.path),
            cfg.resolve(cfg.book.polyglot_path) if cfg.book.polyglot_path else None,
            cfg.book.max_ply,
        )
        self.clock = GameClock(cfg.clock)
        self.jobs: queue.Queue = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, name="engine-worker", daemon=True)
        self.gen = 0
        self._reset_game_state()
        self.phase = "setup"

    # ================================================================ infraestrutura
    def _reset_game_state(self) -> None:
        self.board = chess.Board()
        self.our_color = chess.WHITE
        self.phase = "setup"
        self.model = OpponentModel()
        self.result: str | None = None
        self.result_reason = ""
        self.last_expectation: float | None = None
        self.expected_after_our_move: float | None = None
        self.last_move: dict | None = None
        self.last_opp: dict | None = None
        self.last_opp_hit: bool | None = None
        self.plan: Plan | None = None
        self.live: dict = {}
        self.ponder_live: dict = {}
        self.ponder_search = None
        self.ponder_move: str | None = None
        self.ponder_started = 0.0
        self.draw_claim: str | None = None
        self.think_started = 0.0
        self.think_budget = 0.0
        self.last_score_text = ""
        self.stats = collections.Counter()
        self.modes = collections.Counter()

    def _log(self, msg: str) -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        line = f"{stamp}  {msg}"
        self.events.append(line)
        print(line, flush=True)
        try:
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(dt.date.today().isoformat() + " " + line + "\n")
        except OSError:
            pass

    def start(self) -> None:
        self._log(f"Livro de aberturas: {self.book.source}")
        try:
            self.engine.start()
        except EngineError as exc:
            self._log(f"ATENÇÃO: motor não iniciou ({exc}). Confira engine.path no config.toml.")
        self.worker.start()

    def shutdown(self) -> None:
        self.gen += 1
        self.engine.stop_now()
        self.jobs.put(None)
        self.worker.join(timeout=5)
        self.engine.shutdown()

    def _save(self) -> None:
        data = {
            "version": 1,
            "phase": self.phase,
            "our_color": "white" if self.our_color == chess.WHITE else "black",
            "root_fen": self.board.root().fen(),
            "moves": [m.uci() for m in self.board.move_stack],
            "clock": self.clock.to_dict(),
            "model": self.model.to_dict(),
            "last_expectation": self.last_expectation,
            "expected_after_our_move": self.expected_after_our_move,
            "stats": dict(self.stats),
            "modes": dict(self.modes),
            "result": self.result,
            "saved_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        try:
            self.storage.save(data)
        except OSError as exc:
            self._log(f"Falha ao salvar partida: {exc}")

    # ================================================================ ações da interface
    def new_game(self, color: str, minutes: float | None = None, fen: str | None = None) -> tuple[bool, str]:
        with self.lock:
            try:
                board = chess.Board(fen) if fen else chess.Board()
            except ValueError:
                return False, "FEN inválida."
            if not board.is_valid():
                return False, "Posição inválida."
            self.gen += 1
            self.engine.stop_now()
            self._reset_game_state()
            self.board = board
            self.our_color = chess.WHITE if color == "white" else chess.BLACK
            self.clock.reset(minutes or self.cfg.clock.minutes)
            our_turn = board.turn == self.our_color
            self.clock.start(our_turn)
            self.phase = "pensando" if our_turn else "aguardando"
            self.think_started = time.monotonic()
            self.jobs.put(("newgame", self.gen))
            self._save()
            self._log(f"Nova partida: jogamos de {COLOR_NAME[self.our_color]}.")
            return True, "Partida iniciada."

    def resume(self) -> tuple[bool, str]:
        data = self.storage.load()
        if not data or data.get("phase") in (None, "setup", "fim"):
            return False, "Não há partida em andamento salva."
        with self.lock:
            self.gen += 1
            self.engine.stop_now()
            self._reset_game_state()
            board = chess.Board(data["root_fen"])
            for uci in data.get("moves", []):
                board.push_uci(uci)
            self.board = board
            self.our_color = chess.WHITE if data["our_color"] == "white" else chess.BLACK
            self.clock.load(data.get("clock", {}))
            self.model = OpponentModel.from_dict(data.get("model", {}))
            self.last_expectation = data.get("last_expectation")
            self.expected_after_our_move = data.get("expected_after_our_move")
            self.stats.update(data.get("stats", {}))
            self.modes.update(data.get("modes", {}))
            our_turn = board.turn == self.our_color
            self.clock.running = "ours" if our_turn else "theirs"
            self.phase = "pensando" if our_turn else "aguardando"
            self.think_started = time.monotonic()
            self.jobs.put(("newgame", self.gen))
            self._log(f"Partida retomada no lance {board.fullmove_number}. Sincronize os relógios.")
            return True, "Partida retomada. Sincronize os relógios com o relógio da mesa."

    def opponent_move(self, text: str) -> tuple[bool, str]:
        with self.lock:
            if self.phase != "aguardando":
                return False, {
                    "setup": "Comece uma partida primeiro.",
                    "pensando": "Espere o nosso lance aparecer.",
                    "fim": "A partida terminou.",
                }.get(self.phase, "Agora não é a vez do adversário.")
            try:
                move = parse_move(self.board, text)
            except ValueError as exc:
                return False, str(exc)
            info = describe_move(self.board, move)
            predicted = self.ponder_move
            hit = (move.uci() == predicted) if predicted else None
            used = self.clock.opponent_moved()
            self.model.add(hit, used)
            self.board.push(move)
            self.last_opp = {"uci": move.uci(), **info, "seconds": round(used, 1), "predicted": hit}
            self.last_opp_hit = hit
            if hit:
                self.stats["ponder_hits"] += 1
            self.think_started = time.monotonic()
            if self._check_game_over():
                return True, f"Registrado: {info['say']}. Fim de partida."
            self.phase = "pensando"
            self._save()
            self.jobs.put(("think", self.gen))
            return True, f"Registrado: {info['say']} ({coord_text(move)})"

    def preview(self, text: str) -> dict:
        """Mostra o que seria registrado, sem registrar (usado enquanto o operador digita)."""
        with self.lock:
            if self.phase != "aguardando" or not text.strip():
                return {"ok": False, "msg": ""}
            try:
                move = parse_move(self.board, text)
            except ValueError as exc:
                return {"ok": False, "msg": str(exc)}
            info = describe_move(self.board, move)
            return {"ok": True, "msg": f"Enter registra: {info['say']} ({coord_text(move)})", "uci": move.uci()}

    def undo_opponent(self) -> tuple[bool, str]:
        """Volta para antes do último lance do adversário (corrigir digitação errada)."""
        with self.lock:
            if self.phase == "setup":
                return False, "Nenhuma partida em andamento."
            root_turn = self.board.root().turn
            movers = [root_turn if i % 2 == 0 else not root_turn for i in range(len(self.board.move_stack))]
            if not any(m != self.our_color for m in movers):
                return False, "Não há lance do adversário para corrigir."
            self.gen += 1
            self.engine.stop_now()
            while self.board.move_stack:
                self.board.pop()
                if self.board.turn != self.our_color:
                    break
            self.model.undo()
            self.result = None
            self.phase = "aguardando"
            self.ponder_move = None
            self.last_move = None
            self.last_opp = None
            self.expected_after_our_move = None
            self.clock.running = "theirs"
            self.jobs.put(("ponder", self.gen))
            self._save()
            self._log("Último lance do adversário desfeito. Registre o lance correto.")
            return True, "Desfeito. Registre o lance correto do adversário e sincronize o relógio se precisar."

    def play_now(self) -> tuple[bool, str]:
        with self.lock:
            if self.phase != "pensando":
                return False, "O motor não está pensando agora."
            self.engine.stop_now()
            return True, "Jogando o melhor lance encontrado até agora."

    def sync_clocks(self, ours: str, theirs: str) -> tuple[bool, str]:
        try:
            o, t = _parse_clock(ours), _parse_clock(theirs)
        except ValueError:
            return False, "Use o formato mm:ss."
        with self.lock:
            self.clock.sync(o, t)
            self._save()
        return True, "Relógios sincronizados."

    def draw_offer(self) -> tuple[bool, str]:
        with self.lock:
            e = self.last_expectation if self.last_expectation is not None else 0.5
            limit = self.cfg.strategy.accept_draw_below
            if e < limit:
                self._log(f"Oferta de empate: ACEITAR (expectativa {e:.2f}).")
                return True, "Aceitem o empate. Falem em voz alta: aceitamos o empate."
            self._log(f"Oferta de empate: RECUSAR (expectativa {e:.2f}).")
            return True, "Recusem o empate. Falem em voz alta: não aceitamos, a partida continua."

    def finish(self, result: str, reason: str) -> tuple[bool, str]:
        """Registra fim decidido fora do tabuleiro (tempo, árbitro, empate acordado)."""
        if result not in ("1-0", "0-1", "1/2-1/2"):
            return False, "Resultado inválido."
        with self.lock:
            self.gen += 1
            self.engine.stop_now()
            self._end(result, reason or "registrado pelo operador")
        return True, "Resultado registrado."

    # ================================================================ fim de partida
    def _check_game_over(self) -> bool:
        outcome = self.board.outcome(claim_draw=False)
        if outcome is None:
            return False
        reasons = {
            chess.Termination.CHECKMATE: "xeque-mate",
            chess.Termination.STALEMATE: "afogamento",
            chess.Termination.INSUFFICIENT_MATERIAL: "material insuficiente",
            chess.Termination.SEVENTYFIVE_MOVES: "regra dos 75 lances",
            chess.Termination.FIVEFOLD_REPETITION: "repetição quíntupla",
        }
        self._end(outcome.result(), reasons.get(outcome.termination, outcome.termination.name))
        return True

    def _end(self, result: str, reason: str) -> None:
        self.clock.stop()
        self.phase = "fim"
        self.result = result
        self.result_reason = reason
        self.draw_claim = None
        self.ponder_move = None
        try:
            path = self.storage.archive_pgn(self.board, self.our_color == chess.WHITE, result, reason)
            self._log(f"Partida encerrada: {result} ({reason}). PGN salvo em {path.name}.")
        except OSError as exc:
            self._log(f"Partida encerrada: {result} ({reason}). Falha ao salvar PGN: {exc}")
        self._save()

    # ================================================================ thread do motor
    def _worker_loop(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                break
            kind, gen = job
            if gen != self.gen:
                continue
            try:
                if kind == "newgame":
                    self._job_newgame(gen)
                elif kind == "think":
                    self._job_think(gen)
                elif kind == "ponder":
                    self._job_ponder(gen)
            except Exception as exc:  # nunca deixar a thread morrer
                self._log(f"Erro interno em '{kind}': {exc!r}")
                traceback.print_exc()
                if kind == "think":
                    self._emergency(gen)

    def _stop_ponder(self):
        search = self.ponder_search
        self.ponder_search = None
        if search is None:
            return None
        return self.engine.stop_infinite(search)

    def _job_newgame(self, gen: int) -> None:
        self._stop_ponder()
        self.engine.new_game()
        with self.lock:
            if gen != self.gen:
                return
            if self.phase == "pensando":
                self.jobs.put(("think", gen))
            elif self.phase == "aguardando":
                self.jobs.put(("ponder", gen))

    def _job_ponder(self, gen: int) -> None:
        self._stop_ponder()
        if not self.cfg.engine.ponder:
            return
        with self.lock:
            if gen != self.gen or self.phase != "aguardando":
                return
            fen = self.board.root().fen()
            moves = [m.uci() for m in self.board.move_stack]
            predicted = self.ponder_move
            if predicted:
                moves = moves + [predicted]
            self.ponder_live = {"predicted": predicted, "depth": 0}
        self.ponder_started = time.monotonic()
        self.ponder_search = self.engine.start_infinite(fen, moves, on_info=self._ponder_info_cb(gen))

    def _ponder_info_cb(self, gen: int):
        def cb(line: PvLine) -> None:
            if gen != self.gen:
                return
            if line.multipv == 1:
                self.ponder_live = {**self.ponder_live, "depth": line.depth, "nps": line.nps}
        return cb

    def _think_info_cb(self, gen: int):
        def cb(line: PvLine) -> None:
            if gen != self.gen:
                self.engine.stop_now()
                return
            if line.multipv == 1:
                self.live = {
                    "depth": line.depth,
                    "seldepth": line.seldepth,
                    "nps": line.nps,
                    "nodes": line.nodes,
                    "tbhits": line.tbhits,
                    "pv": line.pv[:8],
                    "cp": line.cp,
                    "mate": line.mate,
                    "wdl": line.wdl,
                }
        return cb

    def _job_think(self, gen: int) -> None:
        ponder_res = self._stop_ponder()
        ponder_elapsed = time.monotonic() - self.ponder_started if ponder_res else 0.0

        with self.lock:
            if gen != self.gen or self.phase != "pensando":
                return
            board = self.board.copy()
            fen = board.root().fen()
            moves = [m.uci() for m in board.move_stack]
            hit = bool(self.last_opp_hit)
            ours, theirs = self.clock.live()
            profile = self.model.profile(self.cfg.strategy)
            self.live = {}
            self.draw_claim = None

        # 1) livro de aberturas
        if self.cfg.book.enabled:
            book_mv = self.book.lookup(board)
            if book_mv:
                entry = self.book.positions.get(book_key(board), {})
                exp = None
                if "cp" in entry:
                    exp = expectation(PvLine(cp=int(entry["cp"])), board.ply())
                self.model.set_loss(self.expected_after_our_move, exp)
                self._commit(gen, board, book_mv, "livro", None, None, "livro de aberturas", exp)
                return

        legal_count = board.legal_moves.count()
        plan = decide_plan(profile, self.last_expectation, ours, theirs, self.cfg.strategy.adaptive,
                           self.cfg.clock.panic_s)
        budget = think_time(self.cfg.clock, ours, board.fullmove_number, legal_count, plan.time_factor)
        with self.lock:
            self.plan = plan
            self.think_budget = budget

        # 2) acerto do ponder: a posição atual já foi analisada no tempo do adversário
        if hit and ponder_res is not None and ponder_res.lines.get(1):
            pl = ponder_res.lines[1]
            remaining = budget - ponder_elapsed
            if (
                plan.multipv == 1
                and remaining <= self.cfg.clock.min_think_s
                and pl.depth >= 16
                and ponder_res.bestmove
                and chess.Move.from_uci(ponder_res.bestmove) in board.legal_moves
            ):
                exp = expectation(pl, board.ply())
                with self.lock:
                    if gen != self.gen:
                        return
                    self.model.set_loss(self.expected_after_our_move, exp)
                pred = pl.pv[1] if len(pl.pv) > 1 else ponder_res.ponder
                self._commit(gen, board, ponder_res.bestmove, "ponder", pl, plan,
                             f"ponder acertou (prof. {pl.depth})", exp, pred)
                return
            floor = self.cfg.clock.min_think_s if plan.multipv == 1 else budget * 0.4
            budget = max(floor, remaining)
            with self.lock:
                self.think_budget = budget

        # 3) busca
        try:
            res = self.engine.search(fen, moves, budget, plan.multipv, on_info=self._think_info_cb(gen))
        except EngineError as exc:
            self._log(f"Motor indisponível ({exc}); usando busca de emergência.")
            self._emergency(gen)
            return

        with self.lock:
            if gen != self.gen:
                return
        best = res.lines.get(1)
        exp_now = expectation(best, board.ply()) if best else None
        # empate reivindicável: o software decide se pede (nunca quando estamos ganhando)
        claim_ok = exp_now is not None and (
            exp_now <= 0.45
            or (exp_now <= 0.6 and ours < theirs)
            or (exp_now <= 0.7 and ours < self.cfg.clock.panic_s)
        )
        with self.lock:
            self.model.set_loss(self.expected_after_our_move, exp_now)
            if claim_ok and (board.is_repetition(3) or board.can_claim_fifty_moves()):
                self.draw_claim = "PARE. Não mova a peça ainda. Fale para o árbitro: pedimos empate, a posição se repetiu. Se ele não aceitar, aí sim mova a peça da tela."

        try:
            mv, line, reason = choose_move(board, res.lines, plan, res.bestmove)
        except ValueError:
            self._emergency(gen)
            return
        if chess.Move.from_uci(mv) not in board.legal_moves:
            self._log(f"Motor devolveu lance ilegal {mv}; usando busca de emergência.")
            self._emergency(gen)
            return
        if claim_ok and self.draw_claim is None:
            after = board.copy(stack=True)
            after.push_uci(mv)
            if after.is_repetition(3):
                with self.lock:
                    self.draw_claim = "Antes de mover, fale para o árbitro: este lance repete a posição e pedimos empate. Se ele não aceitar, mova a peça da tela."
        exp_chosen = expectation(line, board.ply()) if line else exp_now
        predicted = line.pv[1] if line and len(line.pv) > 1 else (res.ponder if mv == res.bestmove else None)
        self._commit(gen, board, mv, "motor", line, plan, reason, exp_chosen, predicted)

    def _emergency(self, gen: int) -> None:
        with self.lock:
            if gen != self.gen or self.phase != "pensando":
                return
            board = self.board.copy()
        mv = emergency_move(board, 0.4)
        self.stats["emergency_moves"] += 1
        self._commit(gen, board, mv, "emergência", None, None, "busca de emergência", None)

    def _commit(
        self,
        gen: int,
        board: chess.Board,
        uci: str,
        source: str,
        line: PvLine | None,
        plan: Plan | None,
        reason: str,
        exp: float | None,
        predicted: str | None = None,
    ) -> None:
        with self.lock:
            if gen != self.gen or self.phase != "pensando":
                return
            move = chess.Move.from_uci(uci)
            if move not in self.board.legal_moves:
                self._log(f"Lance {uci} não é legal na posição atual; descartado.")
                return
            info = describe_move(self.board, move)
            think = time.monotonic() - self.think_started
            self.board.push(move)
            self.clock.we_moved()
            if exp is not None:
                self.last_expectation = exp
            if line is not None and line.mate is not None:
                self.last_score_text = f"M{line.mate}" if line.mate > 0 else f"-M{-line.mate}"
            elif line is not None and line.cp is not None:
                self.last_score_text = f"{line.cp / 100:+.2f}"
            self.expected_after_our_move = exp
            self.stats[f"{source}_moves"] += 1
            if plan:
                self.modes[plan.mode] += 1
            if self.board.is_repetition(3):
                info["notes"].append("Este lance repete a posição pela 3ª vez.")
            self.last_move = {
                "uci": uci,
                **info,
                "source": source,
                "reason": reason,
                "think": round(think, 1),
                "depth": line.depth if line else None,
                "mode": plan.label if plan else ("Livro" if source == "livro" else source.capitalize()),
                "ply": self.board.ply(),
            }
            self.ponder_move = None
            if predicted:
                try:
                    pm = chess.Move.from_uci(predicted)
                    if pm in self.board.legal_moves:
                        self.ponder_move = predicted
                except ValueError:
                    pass
            self._log(f"Jogamos {info['san_pt']} ({source}, {think:.1f}s, {reason}).")
            if self._check_game_over():
                return
            self.phase = "aguardando"
            self._save()
            self.jobs.put(("ponder", gen))

    # ================================================================ estado para a interface
    def _score_text(self) -> tuple[str, float | None]:
        live = self.live
        if self.phase == "pensando" and (live.get("cp") is not None or live.get("mate") is not None):
            if live.get("mate") is not None:
                m = live["mate"]
                return (f"M{m}" if m > 0 else f"-M{-m}"), (1.0 if m > 0 else 0.0)
            cp = live["cp"]
            exp = expectation(PvLine(cp=cp, wdl=live.get("wdl")), self.board.ply())
            return f"{cp / 100:+.2f}", exp
        if self.last_expectation is not None:
            return self.last_score_text, self.last_expectation
        return "", None

    def state(self) -> dict:
        with self.lock:
            ours, theirs = self.clock.live()
            board = self.board
            legal = []
            if self.phase == "aguardando":
                legal = [m.uci() for m in board.legal_moves]
            # lista de lances em notação portuguesa
            replay = board.root().copy()
            sans: list[str] = []
            for mv in board.move_stack:
                sans.append(san_pt(replay.san(mv)))
                replay.push(mv)
            pv_san = []
            if self.live.get("pv"):
                tmp = board.copy()
                for u in self.live["pv"][:6]:
                    try:
                        mv = chess.Move.from_uci(u)
                        if mv not in tmp.legal_moves:
                            break
                        pv_san.append(san_pt(tmp.san(mv)))
                        tmp.push(mv)
                    except ValueError:
                        break
            predicted = None
            if self.phase == "aguardando" and self.ponder_move:
                try:
                    pm = chess.Move.from_uci(self.ponder_move)
                    if pm in board.legal_moves:
                        d = describe_move(board, pm)
                        predicted = {"uci": pm.uci(), "say": d["say"], "san_pt": d["san_pt"], "coord": coord_text(pm)}
                except ValueError:
                    pass
            score_text, exp = self._score_text()
            warnings = []
            if self.phase in ("pensando", "aguardando"):
                if ours < self.cfg.clock.panic_s:
                    warnings.append("Nosso tempo está acabando. Movam a peça e apertem o relógio depressa.")
                if self.engine.status != "ok":
                    warnings.append(f"Motor: {self.engine.status}.")
            eng = self.engine.engine
            saved = self.storage.load() if self.phase == "setup" else None
            return {
                "phase": self.phase,
                "our_color": "white" if self.our_color == chess.WHITE else "black",
                "fen": board.fen(),
                "turn": "ours" if board.turn == self.our_color else "theirs",
                "legal": legal,
                "moves": sans,
                "start_black": board.root().turn == chess.BLACK,
                "start_fullmove": board.root().fullmove_number,
                "last_move": self.last_move,
                "last_opp": self.last_opp,
                "predicted": predicted,
                "in_check": board.is_check(),
                "clock": {"ours": ours, "theirs": theirs, "ours_text": _fmt_clock(ours),
                          "theirs_text": _fmt_clock(theirs), "running": self.clock.running},
                "thinking": {
                    "elapsed": round(time.monotonic() - self.think_started, 1) if self.phase == "pensando" else None,
                    "budget": round(self.think_budget, 1),
                    "depth": self.live.get("depth"),
                    "nps": self.live.get("nps"),
                    "tbhits": self.live.get("tbhits"),
                    "pv": pv_san,
                },
                "ponder": {**self.ponder_live, "active": self.ponder_search is not None},
                "eval": {"text": score_text, "expectation": exp},
                "plan": {"mode": self.plan.mode, "label": self.plan.label} if self.plan else None,
                "opponent": self.model.summary(self.cfg.strategy),
                "engine": {
                    "status": self.engine.status,
                    "name": eng.name if eng else None,
                    "restarts": self.engine.restarts,
                    "threads": self.cfg.engine.resolved_threads(),
                    "hash_mb": self.cfg.engine.resolved_hash(),
                    "tablebases": eng.tablebase_msg if eng else "",
                },
                "book": self.book.source,
                "stats": dict(self.stats),
                "modes": {MODE_LABEL.get(k, k): v for k, v in self.modes.items()},
                "events": list(self.events)[-14:],
                "result": self.result,
                "result_reason": self.result_reason,
                "draw_claim": self.draw_claim,
                "warnings": warnings,
                "resume_available": bool(saved and saved.get("phase") in ("pensando", "aguardando")),
                "resume_info": (f"{len(saved.get('moves', []))} meios-lances, salva às {saved.get('saved_at', '')[11:16]}"
                                if saved else ""),
                "default_minutes": self.cfg.clock.minutes,
            }
