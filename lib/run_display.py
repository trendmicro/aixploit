#!/usr/bin/env python3
"""Live terminal dashboard for an AIxploit run.

Designed to be screenshot-friendly for writeups: scenario, progress, confirmed
exploit counts, per-model hit rate, and the saved heatmap path.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from lib.heatmap import project_title

try:
  from rich import box
  from rich.console import Console, Group, RenderableType
  from rich.live import Live
  from rich.panel import Panel
  from rich.table import Table
  from rich.text import Text
  HAS_RICH = True
except ImportError:
  HAS_RICH = False


@dataclass
class _ModelStat:
  hits: int = 0
  misses: int = 0
  errors: int = 0
  skipped: int = 0
  running: Set[str] = field(default_factory=set)


class RunDisplay:
  """Thread-safe live dashboard covering one aixploit.py invocation."""

  def __init__(
    self,
    test_name: str,
    models: List[str],
    n_prompts: int,
    max_workers: int,
  ) -> None:
    self.test_name = test_name
    self.title = project_title(test_name)
    self.models = list(models)
    self.n_prompts = n_prompts
    self.max_workers = max_workers
    self.total = len(self.models) * n_prompts
    self.heatmap_path = ""

    self._lock = threading.Lock()
    self._by_model = {m: _ModelStat() for m in self.models}
    self._started_at: Optional[float] = None
    self._live: Any = None
    self._stop = threading.Event()
    self._fallback_thread: Optional[threading.Thread] = None
    self._fallback_lines = 0
    self._use_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())

  def __enter__(self) -> "RunDisplay":
    self._started_at = time.monotonic()
    if HAS_RICH and self._use_tty:
      console = Console(highlight=False, width=100, soft_wrap=False)
      self._live = Live(
        self,
        console=console,
        refresh_per_second=4,
        transient=False,
        redirect_stdout=False,
        redirect_stderr=False,
      )
      self._live.start()
    elif not HAS_RICH and self._use_tty:
      self._fallback_thread = threading.Thread(target=self._fallback_loop, daemon=True)
      self._fallback_thread.start()
    elif not HAS_RICH:
      sys.stdout.write(self._render_plain() + "\n")
      sys.stdout.flush()
    return self

  def __exit__(self, exc_type, exc, tb) -> None:
    self._stop.set()
    if self._live is not None:
      try:
        self._live.update(self._build_rich(), refresh=True)
      except Exception:
        pass
      self._live.stop()
      self._live = None
    elif HAS_RICH:
      Console(highlight=False, width=100, soft_wrap=False).print(self._build_rich())
    elif self._fallback_thread is not None:
      self._fallback_thread.join(timeout=1.0)
      self._draw_plain(final=True)
    else:
      sys.stdout.write("\n" + self._render_plain() + "\n")
      sys.stdout.flush()

  def set_heatmap_path(self, path: str) -> None:
    with self._lock:
      self.heatmap_path = path

  def record_skip(self, model: str, test_id: str, exploit_exists: bool) -> None:
    with self._lock:
      stat = self._stat(model)
      stat.skipped += 1
      if exploit_exists:
        stat.hits += 1
      else:
        stat.misses += 1

  def record_start(self, model: str, test_id: str) -> None:
    with self._lock:
      self._stat(model).running.add(str(test_id))

  def record_result(self, model: str, test_id: str, result: Any) -> None:
    kind = _classify_result(result)
    with self._lock:
      stat = self._stat(model)
      stat.running.discard(str(test_id))
      if kind == "HIT":
        stat.hits += 1
      elif kind == "miss":
        stat.misses += 1
      elif kind == "skip":
        stat.skipped += 1
        stat.misses += 1
      else:
        stat.errors += 1

  def record_error(self, model: str, test_id: str, message: str) -> None:
    with self._lock:
      stat = self._stat(model)
      stat.running.discard(str(test_id))
      stat.errors += 1

  def _stat(self, model: str) -> _ModelStat:
    if model not in self._by_model:
      self._by_model[model] = _ModelStat()
      if model not in self.models:
        self.models.append(model)
    return self._by_model[model]

  def __rich__(self) -> RenderableType:
    return self._build_rich()

  def _snapshot(self) -> Dict[str, Any]:
    with self._lock:
      models = []
      hits = misses = errors = skipped = running = 0
      for name in self.models:
        stat = self._by_model[name]
        running_ids = sorted(stat.running, key=_id_sort_key)
        models.append(
          {
            "name": name,
            "hits": stat.hits,
            "misses": stat.misses,
            "errors": stat.errors,
            "skipped": stat.skipped,
            "running_ids": running_ids,
          }
        )
        hits += stat.hits
        misses += stat.misses
        errors += stat.errors
        skipped += stat.skipped
        running += len(running_ids)
      heatmap_path = self.heatmap_path
    elapsed = 0.0 if self._started_at is None else time.monotonic() - self._started_at
    settled = hits + misses + errors
    remaining = max(0, self.total - settled - running)
    evaluated = hits + misses
    return {
      "models": models,
      "hits": hits,
      "misses": misses,
      "errors": errors,
      "skipped": skipped,
      "running": running,
      "settled": settled,
      "remaining": remaining,
      "evaluated": evaluated,
      "elapsed": elapsed,
      "heatmap_path": heatmap_path,
    }

  def _build_rich(self) -> RenderableType:
    snap = self._snapshot()
    header = Text()
    header.append("AIxploit", style="bold cyan")
    header.append("  ·  ", style="dim")
    header.append(self.title, style="bold")
    meta = Text(
      f"{len(self.models)} models × {self.n_prompts} prompts"
      f"   {self.max_workers} worker{'s' if self.max_workers != 1 else ''}"
      f"   elapsed {_fmt_elapsed(snap['elapsed'])}",
      style="dim",
    )

    kpis = Table.grid(expand=True, padding=(0, 2))
    kpis.add_column(justify="center")
    kpis.add_column(justify="center")
    kpis.add_column(justify="center")
    kpis.add_column(justify="center")
    kpis.add_column(justify="center")
    kpis.add_row(
      Text("Confirmed", style="dim"),
      Text("Evaluated", style="dim"),
      Text("Hit rate", style="dim"),
      Text("Running", style="dim"),
      Text("Remaining", style="dim"),
    )
    hit_rate = _fmt_rate(snap["hits"], snap["evaluated"])
    hit_style = "bold red" if snap["hits"] else "bold"
    kpis.add_row(
      Text(str(snap["hits"]), style=hit_style),
      Text(str(snap["evaluated"]), style="bold"),
      Text(hit_rate, style="bold cyan" if snap["evaluated"] else "dim"),
      Text(str(snap["running"]), style="bold"),
      Text(str(snap["remaining"]), style="bold"),
    )

    progress = Text(_progress_bar(snap["settled"], self.total, width=36))
    progress.append(f"  {snap['settled']}/{self.total}", style="dim")
    if snap["errors"]:
      progress.append(f"   {snap['errors']} errors", style="yellow")

    model_table = Table(
      box=box.SIMPLE,
      expand=True,
      pad_edge=False,
      header_style="bold",
      show_edge=False,
    )
    model_table.add_column("Model", ratio=3, no_wrap=True)
    model_table.add_column("Eval", justify="right")
    model_table.add_column("Hits", justify="right")
    model_table.add_column("Rate", justify="right")
    model_table.add_column("Status", ratio=2, overflow="ellipsis")

    for row in snap["models"]:
      evaluated = row["hits"] + row["misses"]
      rate = _fmt_rate(row["hits"], evaluated)
      status = _status_text(row, self.n_prompts)
      hit_cell = Text(str(row["hits"]))
      if row["hits"]:
        hit_cell.stylize("bold red")
      model_table.add_row(
        row["name"],
        str(evaluated),
        hit_cell,
        rate,
        status,
      )

    footer = Text()
    if snap["heatmap_path"]:
      footer.append(f"Heatmap  {snap['heatmap_path']}", style="dim")
    elif snap["errors"]:
      footer.append("Errors are written to aixploit.log", style="dim")

    body_parts = [
      header,
      meta,
      Text(""),
      kpis,
      Text(""),
      progress,
      Text(""),
      model_table,
    ]
    if footer.plain:
      body_parts.extend([Text(""), footer])

    return Panel(
      Group(*body_parts),
      title="AIxploit",
      title_align="left",
      subtitle=self.test_name,
      subtitle_align="right",
      border_style="cyan",
      padding=(1, 1),
    )

  def _render_plain(self) -> str:
    snap = self._snapshot()
    lines = [
      "─" * 72,
      f" AIxploit  ·  {self.title}",
      (
        f" {len(self.models)} models × {self.n_prompts} prompts  ·  "
        f"{self.max_workers} worker{'s' if self.max_workers != 1 else ''}  ·  "
        f"{_fmt_elapsed(snap['elapsed'])}"
      ),
      "─" * 72,
      (
        f" Confirmed {snap['hits']:<5}  Evaluated {snap['evaluated']:<5}  "
        f"Hit rate {_fmt_rate(snap['hits'], snap['evaluated']):<7}  "
        f"Running {snap['running']:<4}  Remaining {snap['remaining']}"
      ),
      f" {_progress_bar(snap['settled'], self.total, width=42)}  "
      f"{snap['settled']}/{self.total} complete",
      "",
      f" {'Model':<24} {'Eval':>6} {'Hits':>6} {'Rate':>8}  Status",
    ]
    for row in snap["models"]:
      evaluated = row["hits"] + row["misses"]
      lines.append(
        f" {row['name']:<24} {evaluated:>6} {row['hits']:>6} "
        f"{_fmt_rate(row['hits'], evaluated):>8}  {_status_text(row, self.n_prompts)}"
      )
    if snap["heatmap_path"]:
      lines.append("")
      lines.append(f" Heatmap  {snap['heatmap_path']}")
    lines.append("─" * 72)
    return "\n".join(lines)

  def _fallback_loop(self) -> None:
    while not self._stop.wait(0.25):
      self._draw_plain(final=False)

  def _draw_plain(self, final: bool) -> None:
    text = self._render_plain()
    lines = text.splitlines()
    out = sys.stdout
    if self._fallback_lines and self._use_tty:
      out.write(f"\033[{self._fallback_lines}A\033[J")
    out.write(text)
    if not text.endswith("\n"):
      out.write("\n")
    out.flush()
    self._fallback_lines = 0 if final else len(lines)


def _classify_result(result: Any) -> str:
  if result is None:
    return "skip"
  if result is False:
    return "error"
  if isinstance(result, dict):
    if result.get("exploit_success"):
      return "HIT"
    status = result.get("status", "success")
    if status == "success":
      return "miss"
    return "error"
  if result:
    return "miss"
  return "error"


def _fmt_rate(hits: int, evaluated: int) -> str:
  if evaluated <= 0:
    return "—"
  return f"{100.0 * hits / evaluated:.1f}%"


def _fmt_elapsed(seconds: float) -> str:
  total = int(max(0, seconds))
  hours, rem = divmod(total, 3600)
  minutes, secs = divmod(rem, 60)
  if hours:
    return f"{hours:d}:{minutes:02d}:{secs:02d}"
  return f"{minutes:02d}:{secs:02d}"


def _progress_bar(done: int, total: int, width: int = 40) -> str:
  if total <= 0:
    filled = 0
  else:
    filled = int(round(width * min(done, total) / total))
    filled = min(width, max(0, filled))
  return "[" + "█" * filled + "░" * (width - filled) + "]"


def _status_text(row: Dict[str, Any], n_prompts: int) -> str:
  running_ids = row["running_ids"]
  if running_ids:
    shown = ", ".join(f"#{i}" for i in running_ids[:3])
    extra = f" +{len(running_ids) - 3}" if len(running_ids) > 3 else ""
    return f"running {shown}{extra}"
  settled = row["hits"] + row["misses"] + row["errors"]
  if n_prompts and settled >= n_prompts:
    return "done"
  return "queued"


def _id_sort_key(sample_id: str):
  try:
    return (0, int(sample_id))
  except (TypeError, ValueError):
    return (1, str(sample_id))
