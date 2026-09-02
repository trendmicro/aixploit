#!/usr/bin/env python3
"""Centralized path management for the framework."""

import os
from typing import Optional

# Calculate framework root once at module load
_FRAMEWORK_ROOT: Optional[str] = None

def _get_framework_root() -> str:
  """Get the framework root directory (blackbox/framework/)."""
  global _FRAMEWORK_ROOT
  if _FRAMEWORK_ROOT is None:
    # This file is in lib/, so go up one level
    _FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  return _FRAMEWORK_ROOT

def get_framework_root() -> str:
  """Get framework root as string path."""
  return _get_framework_root()

# Key directories (calculated once, cached)
def tests_dir() -> str:
  """Get test directory (contains all test-specific code and resources)."""
  return os.path.join(_get_framework_root(), "tests")

def runs_dir(runs_root: str, test_name: str, model: str, test_id: str) -> str:
  """Get run directory for a specific test."""
  return os.path.join(runs_root, test_name, model, f"run-{test_id}")

def exploits_dir(exploits_root: str, test_name: str, model: str, test_id: str) -> str:
  """Get exploits directory for a model."""
  return os.path.join(exploits_root, test_name, model, f"run-{test_id}")

def test_config_path(test_name: str) -> str:
  """Get path to test config file."""
  return os.path.join(tests_dir(), test_name, "test_config.yaml")

def resolve_path(path: str, base: Optional[str] = None) -> str:
  """
  Resolve a path relative to base (or framework root if not specified).
  
  Args:
    path: Path string (can be relative or absolute)
    base: Base directory for relative paths (defaults to framework root)
  
  Returns:
    Resolved path string
  """
  if base is None:
    base = _get_framework_root()
  
  if os.path.isabs(path):
    return os.path.abspath(path)
  return os.path.abspath(os.path.join(base, path))

