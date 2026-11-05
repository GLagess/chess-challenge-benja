"""Gerenciador do motor: mantém o Stockfish vivo durante a partida.

Regras de robustez:
- se o processo morrer, reinicia e repete a busca com tempo reduzido;
- se o binário principal falhar ao iniciar, tenta o binário reserva;
- busca que não termina no prazo é interrompida (stop) e, se preciso, o processo é morto.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .config import Config
from .uci import EngineDead, EngineError, PvLine, Search, SearchResult, UciEngine


class EngineManager:
    def __init__(self, cfg: Config, log: Callable[[str], None] = print):
        self.cfg = cfg
        self.log = log
        self.engine: UciEngine | None = None
        self.restarts = 0
        self.status = "parado"
        paths = [cfg.resolve(cfg.engine.path)]
        if cfg.engine.fallback_path:
            paths.append(cfg.resolve(cfg.engine.fallback_path))
        self.paths: list[Path] = paths
        self.active_path: Path | None = None

    # ---------------------------------------------------------------- ciclo de vida
    def options(self) -> dict:
        e = self.cfg.engine
        opts = {
            "Threads": e.resolved_threads(),
            "Hash": e.resolved_hash(),
            "UCI_ShowWDL": True,
            "Move Overhead": e.move_overhead_ms,
        }
        tb = self.cfg.resolve(e.syzygy_path)
        if tb.is_dir() and any(tb.glob("*.rtbw")):
            opts["SyzygyPath"] = str(tb)
        return opts

    def start(self) -> None:
        last_exc: Exception | None = None
        for path in self.paths:
            try:
                eng = UciEngine(str(path), self.options(), self.cfg.engine.high_priority)
                eng.start()
                self.engine = eng
                self.active_path = path
                self.status = "ok"
                extra = f" ({eng.tablebase_msg})" if eng.tablebase_msg else ""
                e = self.cfg.engine
                self.log(
                    f"Motor pronto: {eng.name} em {path.name}, "
                    f"{e.resolved_threads()} threads, hash {e.resolved_hash()} MB{extra}"
                )
                return
            except Exception as exc:  # tenta o próximo binário
                last_exc = exc
                self.log(f"Falha ao iniciar {path}: {exc}")
        self.status = "falhou"
        raise EngineError(f"nenhum motor pôde ser iniciado: {last_exc}")

    def restart(self, reason: str) -> None:
        self.restarts += 1
        self.status = "reiniciando"
        self.log(f"Reiniciando motor ({reason})")
        if self.engine:
            self.engine.kill()
        self.engine = None
        self.start()

    def ensure(self) -> UciEngine:
        if self.engine is not None and self.engine.is_alive():
            return self.engine
        if self.engine is None:
            self.start()
        else:
            self.restart("processo não está rodando")
        return self.engine

    def shutdown(self) -> None:
        if self.engine:
            self.engine.quit()
        self.engine = None
        self.status = "parado"

    def new_game(self) -> None:
        eng = self.ensure()
        try:
            eng.new_game()
        except EngineError as exc:
            self.restart(f"ucinewgame falhou: {exc}")

    # ---------------------------------------------------------------- busca
    def search(
        self,
        fen: str,
        moves: list[str],
        movetime: float,
        multipv: int = 1,
        on_info: Callable[[PvLine], None] | None = None,
    ) -> SearchResult:
        """Busca com tempo fixo. Tenta até 3 vezes, reduzindo o tempo a cada falha."""
        attempt_time = movetime
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                eng = self.ensure()
                search = eng.go(fen, moves, movetime=attempt_time, multipv=multipv, on_info=on_info)
                grace = 3.0 + attempt_time * 0.25
                try:
                    return eng.wait(search, attempt_time + grace)
                except EngineDead:
                    raise
                except EngineError:
                    # passou do prazo: pede para parar e aproveita o que houver
                    eng.stop()
                    return eng.wait(search, 3.0)
            except EngineError as exc:
                last_exc = exc
                self.log(f"Busca falhou (tentativa {attempt + 1}): {exc}")
                try:
                    self.restart(str(exc))
                except EngineError as exc2:
                    last_exc = exc2
                    time.sleep(0.2)
                attempt_time = max(0.2, min(attempt_time, 1.0) * 0.5)
        raise EngineError(f"busca falhou após 3 tentativas: {last_exc}")

    def start_infinite(self, fen: str, moves: list[str], on_info=None) -> Search | None:
        """Inicia análise sem limite (ponder). Nunca lança exceção."""
        try:
            eng = self.ensure()
            return eng.go(fen, moves, infinite=True, multipv=1, on_info=on_info)
        except EngineError as exc:
            self.log(f"Ponder não iniciou: {exc}")
            return None

    def stop_infinite(self, search: Search | None) -> SearchResult | None:
        if search is None or self.engine is None:
            return None
        try:
            self.engine.stop()
            return self.engine.wait(search, 3.0)
        except EngineError as exc:
            self.log(f"Ponder não parou: {exc}")
            try:
                self.restart("ponder travado")
            except EngineError:
                pass
            return None

    def stop_now(self) -> None:
        """Interrompe a busca atual (usado por 'Jogar agora', desfazer e nova partida)."""
        if self.engine:
            self.engine.stop()
