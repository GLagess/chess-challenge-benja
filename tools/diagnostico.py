"""Diagnóstico do notebook para adaptar a configuração do sistema.

    python tools/diagnostico.py            # mede e mostra o relatório (cerca de 1 minuto)
    python tools/diagnostico.py --aplicar  # mede e grava threads/hash sugeridos no config.toml

O relatório também fica salvo em saves/diagnostico.txt. Copie o bloco entre as
linhas "COPIE DAQUI" e "ATÉ AQUI" e envie para quem está ajustando o sistema.

Rode com o notebook do jeito que vai estar no torneio: na tomada, modo de energia
"Melhor desempenho" e outros programas fechados.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FEN = "r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N2N2/PP2BPPP/R2QKB1R w KQ - 0 9"


# ------------------------------------------------------------------ hardware
def cpu_name() -> str:
    try:
        if os.name == "nt":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "?"


def physical_cores() -> str:
    if os.name != "nt":
        return "?"
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        return out or "?"
    except Exception:
        return "?"


def memory_mb() -> tuple[int, int]:
    """(total, disponível) em MB."""
    try:
        if os.name == "nt":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return int(st.ullTotalPhys / 2**20), int(st.ullAvailPhys / 2**20)
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) // 1024
        return info.get("MemTotal", 0), info.get("MemAvailable", 0)
    except Exception:
        return 0, 0


def power_status() -> str:
    if os.name != "nt":
        return "?"
    parts = []
    try:
        import ctypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

        st = SYSTEM_POWER_STATUS()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st))
        parts.append({1: "na tomada", 0: "NA BATERIA"}.get(st.ACLineStatus, "tomada desconhecida"))
    except Exception:
        pass
    try:
        out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"\((.+)\)", out)
        if m:
            parts.append(f"plano {m.group(1)}")
    except Exception:
        pass
    return ", ".join(parts) or "?"


# ------------------------------------------------------------------ motor
def nps_run(engine_path: str, threads: int, seconds: float, hash_mb: int = 1024) -> tuple[int, int]:
    from app.uci import UciEngine

    eng = UciEngine(engine_path, {"Threads": threads, "Hash": hash_mb})
    eng.start()
    try:
        eng.new_game()
        res = eng.wait(eng.go(FEN, [], movetime=seconds), seconds + 20)
        line = res.lines.get(1)
        return (line.nps if line else 0), (line.depth if line else 0)
    finally:
        eng.quit()


def hash_alloc_seconds(engine_path: str, hash_mb: int) -> float:
    from app.uci import UciEngine

    eng = UciEngine(engine_path, {"Threads": 1, "Hash": 16})
    eng.start()
    try:
        t = time.monotonic()
        eng.set_option("Hash", hash_mb)
        eng.isready(timeout=180)
        eng.new_game()
        return time.monotonic() - t
    finally:
        eng.quit()


# ------------------------------------------------------------------ config
def apply_config(path: Path, threads: int, hash_mb: int) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^threads\s*=\s*\d+", f"threads = {threads}", text, count=1)
    text = re.sub(r"(?m)^hash_mb\s*=\s*\d+", f"hash_mb = {hash_mb}", text, count=1)
    text = re.sub(r"(?m)^high_priority\s*=\s*\w+", "high_priority = false", text, count=1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="grava threads e hash sugeridos no config.toml")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    from app.config import load_config

    cfg = load_config(args.config)
    engine_path = str(cfg.resolve(cfg.engine.path))
    if not Path(engine_path).is_file():
        print(f"[ERRO] Motor não encontrado em {engine_path}. Rode antes o 1-instalar.bat.")
        return 1

    logical = os.cpu_count() or 1
    total, avail = memory_mb()
    print("Coletando dados do notebook e medindo a velocidade (cerca de 1 minuto)...\n")

    # Não mede "CPU inteira": 18 threads travam o notebook e o --aplicar gravaria isso.
    cap = 12 if logical >= 16 else max(1, logical - 2)
    candidates = sorted({t for t in (max(1, logical // 4), max(1, min(cap, logical // 2)), cap) if 1 <= t <= cap}) or [1]
    speeds: dict[int, tuple[int, int]] = {}
    for t in candidates:
        print(f"  medindo com {t} threads...", flush=True)
        speeds[t] = nps_run(engine_path, t, 6.0)

    usable = [t for t in candidates if t < logical] or candidates
    best = max(usable, key=lambda t: (speeds[t][0], -t))
    # prefere menos threads se a diferença for pequena (sobra CPU para a interface)
    for t in sorted(usable):
        if speeds[t][0] >= 0.95 * speeds[best][0]:
            best = t
            break

    print(f"  teste de aquecimento com {best} threads (3 x 10 s)...", flush=True)
    sustained = [nps_run(engine_path, best, 10.0)[0] for _ in range(3)]
    drop = 1 - sustained[-1] / sustained[0] if sustained[0] else 0.0

    hash_suggest = int(min(16384, total * 0.40, max(1024, avail * 0.5))) if total else 2048
    hash_suggest = max(512, (hash_suggest // 512) * 512)
    print(f"  testando alocação de {hash_suggest} MB de hash...", flush=True)
    alloc = hash_alloc_seconds(engine_path, hash_suggest)

    from app.book import OpeningBook
    tb = cfg.resolve(cfg.engine.syzygy_path)
    n_tb = len(list(tb.glob("*.rtbw"))) if tb.is_dir() else 0
    book = OpeningBook(cfg.resolve(cfg.book.path), None)
    try:
        import chess
        chess_ver = chess.__version__
    except ImportError:
        chess_ver = "?"

    alerts = []
    power = power_status()
    if "BATERIA" in power:
        alerts.append("Notebook na bateria: a velocidade medida não vale para o torneio. Ligue na tomada e rode de novo.")
    if drop > 0.12:
        alerts.append(f"Velocidade caiu {drop:.0%} em 30 s: aquecimento. Use base com cooler e deixe as saídas de ar livres.")
    if avail and avail < total * 0.4:
        alerts.append("Pouca RAM livre: feche outros programas antes da partida.")
    if speeds[best][0] < 5_000_000:
        alerts.append("Velocidade baixa para o torneio. Confira modo de energia e programas abertos.")
    if alloc > 15:
        alerts.append(f"Hash de {hash_suggest} MB demorou {alloc:.0f} s para alocar: use um valor menor.")

    speeds_txt = " | ".join(f"{t} threads: {speeds[t][0] / 1e6:.1f} M/s (prof. {speeds[t][1]})" for t in candidates)
    lines = [
        "===== COPIE DAQUI =====",
        f"Data: {dt.datetime.now():%d/%m/%Y %H:%M}",
        f"Sistema: {platform.platform()}",
        f"CPU: {cpu_name()} | {physical_cores()} núcleos físicos | {logical} lógicos",
        f"RAM: {total / 1024:.1f} GB total | {avail / 1024:.1f} GB livre agora",
        f"Energia: {power}",
        f"Python {platform.python_version()} | python-chess {chess_ver}",
        f"Tablebases: {n_tb} arquivos WDL | Livro: {len(book.positions)} posições",
        f"Velocidade: {speeds_txt}",
        f"Sustentado ({best} threads, 3 x 10 s): " + " / ".join(f"{x / 1e6:.1f}" for x in sustained)
        + f" M/s (queda {drop:.0%})",
        f"Hash {hash_suggest} MB alocado em {alloc:.1f} s",
        f"Config atual: threads={cfg.engine.threads} (efetivo {cfg.engine.resolved_threads()}), "
        f"hash_mb={cfg.engine.hash_mb} (efetivo {cfg.engine.resolved_hash()}), "
        f"high_priority={str(cfg.engine.high_priority).lower()}, ponder={str(cfg.engine.ponder).lower()}, "
        f"entry_lag_s={cfg.clock.entry_lag_s}, exec_lag_s={cfg.clock.exec_lag_s}",
        f"Sugestão: threads = {best}, hash_mb = {hash_suggest}",
    ]
    lines += [f"ALERTA: {a}" for a in alerts]
    lines.append("===== ATÉ AQUI =====")
    report = "\n".join(lines)
    print("\n" + report)

    out = cfg.resolve(cfg.saves_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "diagnostico.txt").write_text(report + "\n", encoding="utf-8")
    print(f"\nRelatório salvo em {out / 'diagnostico.txt'}")

    if args.aplicar:
        cfg_path = Path(args.config) if args.config else ROOT / "config.toml"
        apply_config(cfg_path, best, hash_suggest)
        print(f"Aplicado no {cfg_path.name}: threads = {best}, hash_mb = {hash_suggest}, high_priority = false")
    else:
        print("Para gravar a sugestão no config.toml: python tools\\diagnostico.py --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
