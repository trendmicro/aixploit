#!/usr/bin/env python3
"""Save a binary exploit heatmap (sample id x model) as a PNG."""

import os
import re

from lib.logger import get_logger
from lib.models import display_model_name

logger = get_logger()

_RUN_DIR_RE = re.compile(r"^run-(.+)$")
_PROJECT_TITLES = {
  "kyc": "KYC",
  "postgres": "Postgres-readonly",
  "ransom": "Ransom",
}


def project_title(test_name: str) -> str:
  """Human-readable project name used as the heatmap title."""
  return _PROJECT_TITLES.get(test_name, test_name)


def _sample_sort_key(sample_id):
  try:
    return (0, int(sample_id))
  except (TypeError, ValueError):
    return (1, str(sample_id))


def _iter_model_run_ids(root: str, test_name: str):
  """Yield (model, sample_id) for each run-* folder under root/test_name."""
  project_dir = os.path.join(root, test_name)
  if not os.path.isdir(project_dir):
    return

  for model in os.listdir(project_dir):
    if model.startswith("."):
      continue
    model_dir = os.path.join(project_dir, model)
    if not os.path.isdir(model_dir):
      continue
    for name in os.listdir(model_dir):
      match = _RUN_DIR_RE.match(name)
      if not match:
        continue
      run_path = os.path.join(model_dir, name)
      if os.path.isdir(run_path):
        yield model, match.group(1)


def _collect_matrix(test_name: str, runs: str, exploits: str):
  """Build heatmap axes and a 0/1 matrix from runs/ and exploits/ folders.

  Returns (display_models, sample_ids, matrix) or None if there is nothing
  to plot. display_models are vendor-stripped and sorted. sample_ids are
  the union of run folders under runs/{test_name}. A cell is 1 if any
  vendor-variant of that model has an exploit folder for that sample.
  """
  sample_ids = set()
  models_raw = set()
  for model, sample_id in _iter_model_run_ids(runs, test_name):
    models_raw.add(model)
    sample_ids.add(sample_id)

  if not models_raw or not sample_ids:
    return None

  display_models = sorted({display_model_name(m) for m in models_raw})
  sample_ids = sorted(sample_ids, key=_sample_sort_key)
  sample_index = {sid: j for j, sid in enumerate(sample_ids)}
  model_index = {name: i for i, name in enumerate(display_models)}

  matrix = [[0] * len(sample_ids) for _ in display_models]
  for model, sample_id in _iter_model_run_ids(exploits, test_name):
    i = model_index.get(display_model_name(model))
    j = sample_index.get(sample_id)
    if i is None or j is None:
      continue
    matrix[i][j] = 1

  return display_models, sample_ids, matrix


def save_exploit_heatmap(
  test_name: str,
  runs: str,
  exploits: str,
  heatmap_dir: str = "./heatmap",
) -> str:
  """Write ./heatmap/{test_name}.png and return the output path.

  X-axis is every sample id found under runs/{test_name}. Y-axis is model
  names with vendor suffixes removed (Z–A so later names sit at the top).
  Cells are 1 if an exploit exists, otherwise 0. Navy/teal two-color
  map (from the reference heatmap), fine grid, no colorbar/legend.
  """
  collected = _collect_matrix(test_name, runs, exploits)
  if collected is None:
    logger.warning(
      f"No runs found under {os.path.join(runs, test_name)}; skipping heatmap"
    )
    return ""

  display_models, sample_ids, matrix = collected
  display_models = list(reversed(display_models))
  matrix = list(reversed(matrix))

  try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    import seaborn as sns
  except ImportError:
    logger.error(
      "matplotlib and seaborn are required to save heatmaps. "
      "Install them: pip install matplotlib seaborn"
    )
    return ""

  n_models = len(display_models)
  n_samples = len(sample_ids)
  width = 14.0
  height = max(3.8, n_models * 0.32 + 1.4)
  # Two-color map sampled from the reference heatmap: navy (0) and teal (1).
  cmap = ListedColormap(["#1d2333", "#559ca2"])

  fig, ax = plt.subplots(figsize=(width, height))
  sns.heatmap(
    matrix,
    ax=ax,
    cmap=cmap,
    vmin=0,
    vmax=1,
    cbar=False,
    linewidths=0.05,
    linecolor="#3a4154",
    xticklabels=False,
    yticklabels=display_models,
  )
  ax.set_title(
    f"{project_title(test_name)}:Injected Payload Effectiveness",
    loc="left",
    fontweight="bold",
    fontsize=14,
    pad=12,
  )
  ax.set_xlabel("Sample Number", fontstyle="italic", fontsize=11)
  ax.set_ylabel("Model", fontstyle="italic", fontsize=11)
  ax.set_xticks(_major_tick_positions(sample_ids))
  ax.set_xticklabels(
    _major_tick_labels(sample_ids),
    rotation=45,
    ha="right",
    fontsize=9,
  )
  ax.tick_params(axis="y", length=0, labelsize=9)
  ax.tick_params(axis="x", length=3)
  ax.set_aspect("auto")
  fig.tight_layout()

  os.makedirs(heatmap_dir, exist_ok=True)
  out_path = os.path.join(heatmap_dir, f"{test_name}.png")
  fig.savefig(out_path, dpi=150, bbox_inches="tight")
  plt.close(fig)
  logger.info(f"Saved exploit heatmap to {out_path}")
  return out_path


def _major_sample_step(sample_ids):
  numeric = []
  for sid in sample_ids:
    try:
      numeric.append(int(sid))
    except (TypeError, ValueError):
      continue
  if not numeric:
    return 1
  span = max(numeric) - min(numeric)
  if span >= 100:
    return 50
  if span >= 50:
    return 25
  if span >= 20:
    return 10
  return 1


def _major_tick_positions(sample_ids):
  step = _major_sample_step(sample_ids)
  positions = []
  for j, sid in enumerate(sample_ids):
    try:
      n = int(sid)
    except (TypeError, ValueError):
      continue
    if n % step == 0:
      positions.append(j + 0.5)
  return positions


def _major_tick_labels(sample_ids):
  step = _major_sample_step(sample_ids)
  labels = []
  for sid in sample_ids:
    try:
      n = int(sid)
    except (TypeError, ValueError):
      continue
    if n % step == 0:
      labels.append(str(n))
  return labels
