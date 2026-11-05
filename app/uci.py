"""Cliente UCI próprio.

Escrito do zero (em vez de usar o cliente do python-chess) para termos controle
total de timeout, kill e reinício do processo: no torneio, software travado é derrota.
Toda comunicação com o motor passa por aqui.
"""
from __future__ import annotations

import collections
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


class EngineError(Exception):
    """Falha recuperável na comunicação com o motor."""


class EngineDead(EngineError):
    """O processo do motor terminou."""


@dataclass
class PvLine:
    multipv: int = 1
    depth: int = 0
    seldepth: int = 0
    cp: int | None = None
    mate: int | None = None
    wdl: tuple[int, int, int] | None = None
    bound: str | None = None
    nodes: int = 0
    nps: int = 0
    tbhits: int = 0
    time_ms: int = 0
    pv: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    bestmove: str | None
    ponder: str | None
    lines: dict[int, PvLine]
    elapsed: float


_INT_FIELDS = {"depth", "seldepth", "multipv", "nodes", "nps", "tbhits", "time"}


def parse_info(line: str) -> PvLine | None:
    """Converte uma linha 'info ...' em PvLine. Ignora linhas sem pv/score."""
    tokens = line.split()
    if not tokens or tokens[0] != "info" or "pv" not in tokens or "score" not in tokens:
        return None
    out = PvLine()
    i = 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in _INT_FIELDS and i + 1 < n:
            try:
                val = int(tokens[i + 1])
            except ValueError:
                val = 0
            if tok == "time":
                out.time_ms = val
            else:
                setattr(out, tok, val)
            i += 2
        elif tok == "score" and i + 2 < n:
            kind, val = tokens[i + 1], int(tokens[i + 2])
            if kind == "cp":
                out.cp = val
            elif kind == "mate":
                out.mate = val
            i += 3
            if i < n and tokens[i] in ("lowerbound", "upperbound"):
                out.bound = tokens[i]
                i += 1
        elif tok == "wdl" and i + 3 < n:
            out.wdl = (int(tokens[i + 1]), int(tokens[i + 2]), int(tokens[i + 3]))
            i += 4
        elif tok == "pv":
            out.pv = tokens[i + 1:]
            break
        else:
            i += 1
    return out


class Search:
    """Uma busca em andamento no motor."""

    def __init__(self, on_info: Callable[[PvLine], None] | None):
        self.lines: dict[int, PvLine] = {}
        self.bestmove: str | None = None
        self.ponder: str | None = None
        self.done = threading.Event()
        self.error: Exception | None = None
        self.on_info = on_info
        self.started = time.monotonic()
        self.finished: float | None = None

    def result(self) -> SearchResult:
        end = self.finished or time.monotonic()
        return SearchResult(self.bestmove, self.ponder, dict(self.lines), end - self.started)


class UciEngine:
    def __init__(self, path: str, options: dict | None = None, high_priority: bool = False):
        self.path = path
        self.options = options or {}
        self.high_priority = high_priority
        self.proc: subprocess.Popen | None = None
        self.name = "?"
        self.alive = False
        self.tablebase_msg = ""
        self.last_lines: collections.deque[str] = collections.deque(maxlen=50)
        self._tokens: queue.Queue[str] = queue.Queue()
        self._search: Search | None = None
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._multipv = 1
        self._generation = 0
        self._reader_thread: threading.Thread | None = None

    # ---------------------------------------------------------------- processo
    def start(self, timeout: float = 20.0) -> None:
        if not os.path.exists(self.path):
            raise EngineError(f"Motor não encontrado: {self.path}")
        flags = 0
        if os.name == "nt":
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if self.high_priority:
                flags |= getattr(subprocess, "HIGH_PRIORITY_CLASS", 0)
        self._generation += 1
        generation = self._generation
        self.proc = subprocess.Popen(
            [self.path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
            cwd=os.path.dirname(os.path.abspath(self.path)) or None,
        )
        self.alive = True
        self._reader_thread = threading.Thread(
            target=self._reader, args=(generation, self.proc), name="uci-reader", daemon=True
        )
        self._reader_thread.start()
        self._send("uci")
        self._wait_token("uciok", timeout)
        for name, value in self.options.items():
            self.set_option(name, value)
        self._multipv = int(self.options.get("MultiPV", 1))
        # alocar Hash grande pode levar alguns segundos
        self.isready(timeout=120)

    def is_alive(self) -> bool:
        return bool(self.proc) and self.alive and self.proc.poll() is None

    def kill(self) -> None:
        self.alive = False
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        reader = self._reader_thread
        if reader and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=2)

    def restart(self, timeout: float = 120.0) -> None:
        """Sobe o processo de novo com as mesmas opções. Usado quando o motor cai."""
        self.kill()
        self._tokens = queue.Queue()
        with self._lock:
            self._search = None
        self._multipv = int(self.options.get("MultiPV", 1))
        self.last_lines.clear()
        self.start(timeout=timeout)

    def quit(self) -> None:
        if not self.is_alive():
            return
        try:
            self._send("quit")
            self.proc.wait(timeout=3)
        except Exception:
            pass
        self.kill()

    # ---------------------------------------------------------------- leitura
    def _death_detail(self, prefix: str, proc: subprocess.Popen | None, reader_exc: Exception | None) -> str:
        bits = [prefix]
        code = proc.poll() if proc is not None else None
        if code not in (None, 0):
            bits.append(f"código {code}")
        if reader_exc is not None:
            bits.append(f"leitura: {reader_exc}")
        tail = [
            ln for ln in self.last_lines
            if "CRITICAL" in ln or ln.startswith("info string") or not ln.startswith("info ")
        ]
        tail = (tail or list(self.last_lines))[-3:]
        if tail:
            bits.append("últimas linhas: " + " || ".join(tail))
        return " — ".join(bits)

    def _reader(self, generation: int, proc: subprocess.Popen) -> None:
        reader_exc: Exception | None = None
        try:
            for raw in proc.stdout:
                if generation != self._generation:
                    return
                line = raw.strip()
                if not line:
                    continue
                self.last_lines.append(line)
                if line.startswith("id name "):
                    self.name = line[8:]
                elif line.startswith("info string") and "tablebase" in line.lower():
                    self.tablebase_msg = line[12:]
                if line.startswith("info "):
                    with self._lock:
                        s = self._search
                    if s is not None:
                        pl = parse_info(line)
                        if pl is not None:
                            s.lines[pl.multipv] = pl
                            if s.on_info:
                                try:
                                    s.on_info(pl)
                                except Exception:
                                    pass
                elif line.startswith("bestmove"):
                    parts = line.split()
                    with self._lock:
                        s = self._search
                        self._search = None
                    if s is not None:
                        s.bestmove = parts[1] if len(parts) > 1 and parts[1] != "(none)" else None
                        if len(parts) >= 4 and parts[2] == "ponder":
                            s.ponder = parts[3]
                        s.finished = time.monotonic()
                        s.done.set()
                elif line in ("uciok", "readyok"):
                    self._tokens.put(line)
        except Exception as exc:
            reader_exc = exc
        if generation != self._generation:
            return
        # fim do processo
        self.alive = False
        with self._lock:
            s = self._search
            self._search = None
        if s is not None:
            s.error = EngineDead(self._death_detail("motor terminou durante a busca", proc, reader_exc))
            s.done.set()
        self._tokens.put("EOF")

    def _wait_token(self, token: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise EngineError(f"motor não respondeu '{token}' a tempo")
            try:
                got = self._tokens.get(timeout=left)
            except queue.Empty:
                continue
            if got == "EOF":
                raise EngineDead("motor terminou")
            if got == token:
                return

    # ---------------------------------------------------------------- comandos
    def _send(self, cmd: str) -> None:
        if not self.proc or self.proc.poll() is not None:
            self.alive = False
            raise EngineDead("motor não está rodando")
        with self._write_lock:
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self.alive = False
                raise EngineDead(f"falha ao escrever no motor: {exc}") from exc

    def set_option(self, name: str, value) -> None:
        if isinstance(value, bool):
            value = "true" if value else "false"
        self._send(f"setoption name {name} value {value}")

    def isready(self, timeout: float = 10.0) -> None:
        # descarta tokens velhos
        while not self._tokens.empty():
            try:
                if self._tokens.get_nowait() == "EOF":
                    raise EngineDead("motor terminou")
            except queue.Empty:
                break
        self._send("isready")
        self._wait_token("readyok", timeout)

    def new_game(self, timeout: float = 120.0) -> None:
        self._send("ucinewgame")
        self.isready(timeout)

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._search is not None

    def go(
        self,
        fen: str,
        moves: list[str],
        *,
        movetime: float | None = None,
        infinite: bool = False,
        multipv: int = 1,
        on_info: Callable[[PvLine], None] | None = None,
    ) -> Search:
        if self.busy:
            raise EngineError("motor ocupado com outra busca")
        if multipv != self._multipv:
            # Stockfish 19 encerra o processo se o próximo comando chegar
            # antes de a opção terminar de valer.
            self.set_option("MultiPV", multipv)
            self.isready(timeout=30)
            self._multipv = multipv
        pos = f"position fen {fen}" + (" moves " + " ".join(moves) if moves else "")
        search = Search(on_info)
        with self._lock:
            self._search = search
        try:
            self._send(pos)
            if infinite:
                self._send("go infinite")
            else:
                ms = max(10, int((movetime or 1.0) * 1000))
                self._send(f"go movetime {ms}")
        except EngineError:
            with self._lock:
                self._search = None
            raise
        return search

    def stop(self) -> None:
        try:
            if self.busy:
                self._send("stop")
        except EngineError:
            pass

    def wait(self, search: Search, timeout: float) -> SearchResult:
        if not search.done.wait(timeout):
            raise EngineError("busca passou do tempo limite")
        if search.error:
            raise search.error
        return search.result()
