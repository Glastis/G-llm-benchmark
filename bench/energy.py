"""Strata GPU energy, indicative (PLAN §10.13).

One GPU power sample per second (`nvidia-smi`), written to energy.csv during the run, then
integrated to Wh. The CPU is not measured (RAPL is only readable as root), so the figure
underestimates real consumption.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

QUERY = ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"]


def read_watts() -> float | None:
    try:
        out = subprocess.run(QUERY, capture_output=True, text=True, timeout=5).stdout
        return float(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


class GpuSampler:
    """`with GpuSampler(path):` samples GPU power until the block exits."""

    def __init__(self, path: Path, period_s: float = 1.0, read=read_watts):
        self.path, self.period_s, self.read = path, period_s, read
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> GpuSampler:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()

    def _loop(self) -> None:
        start = time.monotonic()
        with self.path.open("w", encoding="utf-8") as f:
            f.write("t_s,watts\n")
            while True:
                watts = self.read()
                if watts is not None:
                    f.write(f"{time.monotonic() - start:.2f},{watts:.2f}\n")
                    f.flush()
                if self._stop.wait(self.period_s):
                    return


def energy_wh(csv_path: Path) -> float | None:
    """Trapezoidal integral of energy.csv, in Wh. None without at least two samples."""
    if not csv_path.is_file():
        return None
    rows = [tuple(map(float, line.split(","))) for line in csv_path.read_text().splitlines()[1:] if line]
    if len(rows) < 2:
        return None
    joules = sum((t2 - t1) * (w1 + w2) / 2 for (t1, w1), (t2, w2) in zip(rows, rows[1:]))
    return joules / 3600
