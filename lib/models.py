#!/usr/bin/env python3
"""Normalize model names between OpenRouter API and legacy directory conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

_OPENROUTER_RE = re.compile(r"^(anthropic|google|openai)/.+$")
_VENDOR_SUFFIXES = ("-anthropic", "-aws")
_ANTHROPIC_RE = re.compile(r"^claude-(sonnet|opus)-(.+)$")
_GEMINI_MINOR_RE = re.compile(r"^gemini-3\.(\d+)-(.+)$")


@dataclass(frozen=True)
class ModelSpec:
  """Resolved model identifiers."""

  raw: str
  api: str
  dir: str
  display: str


def is_openrouter_name(model: str) -> bool:
  """True when model uses vendor/model OpenRouter naming."""
  return "/" in model and _OPENROUTER_RE.match(model) is not None


def strip_vendor_suffix(model: str) -> str:
  """Remove a trailing vendor suffix such as '-anthropic' or '-aws'."""
  for suffix in sorted(_VENDOR_SUFFIXES, key=len, reverse=True):
    if model.endswith(suffix) and len(model) > len(suffix):
      return model[: -len(suffix)]
  return model


def display_model_name(model: str) -> str:
  """Canonical short label for dashboards and heatmaps."""
  return strip_vendor_suffix(dir_model_name(model))


def dir_model_name(model: str) -> str:
  """Filesystem-safe directory slug for runs/, exploits/, and containers."""
  if is_openrouter_name(model):
    return _openrouter_to_dir(model)
  return model


def api_model_name(model: str) -> str:
  """Model name passed to the Claude CLI --model flag."""
  return model.strip()


def parse_model(raw: str) -> ModelSpec:
  """Resolve a config model entry into API, directory, and display names."""
  raw = raw.strip()
  dir_name = dir_model_name(raw)
  return ModelSpec(
    raw=raw,
    api=api_model_name(raw),
    dir=dir_name,
    display=display_model_name(raw),
  )


def parse_models(models: Iterable[str]) -> List[ModelSpec]:
  """Resolve every model entry from a config file."""
  return [parse_model(model) for model in models]


def _openrouter_to_dir(model: str) -> str:
  vendor, rest = model.split("/", 1)
  if vendor == "anthropic":
    return _anthropic_to_dir(rest)
  if vendor == "google":
    return _google_to_dir(rest)
  if vendor == "openai":
    return rest
  return model.replace("/", "-")


def _anthropic_to_dir(name: str) -> str:
  # claude-sonnet-4 -> claude-4-sonnet
  match = _ANTHROPIC_RE.match(name)
  if match:
    tier, version = match.groups()
    return f"claude-{version}-{tier}"
  return name


def _google_to_dir(name: str) -> str:
  if name.endswith("-preview"):
    name = name[: -len("-preview")]
  match = _GEMINI_MINOR_RE.match(name)
  if match:
    # gemini-3.1-pro -> gemini-3-pro
    return f"gemini-3-{match.group(2)}"
  return name
