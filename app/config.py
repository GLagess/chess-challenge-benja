"""Configuração do sistema: valores padrão + leitura do config.toml."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("Este sistema precisa de Python 3.11 ou mais novo.")

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class EngineConfig:
    path: str = "engines/stockfish.exe"
    fallback_path: str = ""          # binário reserva (ex.: outra cópia ou outra versão)
    threads: int = 0                 # 0 = automático: no máximo 8, para o Windows não ficar sem CPU
    hash_mb: int = 0                 # 0 = automático: até 8 GB. RAM sobrando não evita o travamento.
    syzygy_path: str = "tablebases"
    move_overhead_ms: int = 300      # atraso interno; o atraso humano é tratado no gestor de tempo
    high_priority: bool = False      # prioridade alta rouba CPU da interface; deixe desligado
    ponder: bool = True              # pensar no tempo do adversário

    def resolved_threads(self) -> int:
        if self.threads and self.threads > 0:
            return self.threads
        logical = os.cpu_count() or 2
        # 18 threads num i7 de 20 lógicos deixam o mouse e o navegador sem CPU, com RAM livre.
        if logical >= 12:
            return 12
        if logical >= 6:
            return logical - 2
        return max(1, logical - 1)

    def resolved_hash(self) -> int:
        if self.hash_mb and self.hash_mb > 0:
            return self.hash_mb
        total = total_ram_mb()
        if not total:
            return 2048
        return int(max(1024, min(16384, total * 0.40)))


def total_ram_mb() -> int:
    """RAM total da máquina em MB (0 se não for possível descobrir)."""
    try:
        if os.name == "nt":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys / 1024 / 1024)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 / 1024)
    except Exception:
        return 0


@dataclass
class ClockConfig:
    minutes: float = 25.0
    increment_s: float = 0.0
    entry_lag_s: float = 3.0     # do adversário apertar o relógio até o lance ser registrado aqui
    exec_lag_s: float = 4.0      # do nosso lance aparecer na tela até apertarmos o relógio
    reserve_s: float = 60.0      # reserva intocável para o fim da partida
    min_think_s: float = 0.5
    max_think_s: float = 25.0
    panic_s: float = 120.0       # abaixo disso: lances rápidos
    critical_s: float = 30.0     # abaixo disso: lances quase instantâneos
    moves_to_go_base: float = 75.0   # estimativa de lances restantes: base - inclinação * nº do lance
    moves_to_go_slope: float = 0.5
    min_moves_to_go: float = 40.0    # nunca planejar para menos que isso (finais longos sem acréscimo)


@dataclass
class BookConfig:
    enabled: bool = True
    path: str = "books/livro.json"
    polyglot_path: str = ""      # opcional: livro .bin no formato Polyglot
    max_ply: int = 30


@dataclass
class StrategyConfig:
    adaptive: bool = True
    min_samples: int = 6             # lances do adversário antes de classificar o perfil
    blunder_threshold: float = 0.12  # queda de expectativa que conta como erro grave
    weak_avg_loss: float = 0.045
    strong_avg_loss: float = 0.02
    strong_hit_rate: float = 0.45
    accept_draw_below: float = 0.35  # aceita empate oferecido só se a expectativa for menor que isso


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True


@dataclass
class Config:
    engine: EngineConfig = field(default_factory=EngineConfig)
    clock: ClockConfig = field(default_factory=ClockConfig)
    book: BookConfig = field(default_factory=BookConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    saves_dir: str = "saves"

    def resolve(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else ROOT / path


def _merge(obj, data: dict, prefix: str = "") -> None:
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            print(f"[config] chave desconhecida ignorada: {prefix}{key}")
            continue
        current = getattr(obj, key)
        if is_dataclass(current) and isinstance(value, dict):
            _merge(current, value, f"{prefix}{key}.")
        else:
            setattr(obj, key, type(current)(value) if current is not None else value)


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg = Config()
    cfg_path = Path(path) if path else ROOT / "config.toml"
    if cfg_path.exists():
        with open(cfg_path, "rb") as fh:
            _merge(cfg, tomllib.load(fh))
    return cfg
