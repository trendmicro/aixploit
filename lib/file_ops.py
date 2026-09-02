#!/usr/bin/env python3
"""File operations module for blackbox tests."""

import json
import os
import shutil
from typing import Dict, List, Any, Optional

from lib.paths import get_framework_root, resolve_path, tests_dir
from lib.logger import get_logger

logger = get_logger()


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
  """Load JSONL file and return list of dicts."""
  items = []
  if not os.path.exists(filepath):
    logger.warning(f"File not found: {filepath}")
    return items
  
  with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
      line = line.strip()
      if line:
        try:
          items.append(json.loads(line))
        except json.JSONDecodeError as e:
          logger.error(f"Error parsing JSON line in {filepath}: {e}")
  
  return items


def construct_prompts(prompts_filepath: str) -> List[Dict[str, Any]]:
  """Construct list of test dicts from prompts.jsonl."""
  prompts = load_jsonl(prompts_filepath)
  
  return prompts


def cleanup_data_directory(
  test_name: str,
  context: Dict[str, Any],
  run_dir: str
) -> bool:
  """
  Delete all files and folders copied from setup/data/ in run directory.
  
  Args:
    test_name: Name of the test (directory under tests/)
    context: Context for placeholder resolution (unused, kept for compatibility)
    run_dir: Run directory
  
  Returns:
    True if successful, False otherwise
  """
  # Get data directory: tests/{test_name}/setup/data/
  data_dir = os.path.join(tests_dir(), test_name, "setup", "data")
  
  if not os.path.exists(data_dir):
    logger.warning(f"Data directory not found: {data_dir}, nothing to cleanup")
    return True  # Not an error, just no data was copied
  
  if not os.path.isdir(data_dir):
    logger.warning(f"Data path is not a directory: {data_dir}, nothing to cleanup")
    return True
  
  try:
    # Get list of items that were copied from setup/data/
    items_to_delete = []
    for item_name in os.listdir(data_dir):
      target_path = os.path.join(run_dir, item_name)
      if os.path.exists(target_path):
        items_to_delete.append((item_name, target_path))
    
    # Delete each item from run_dir
    for item_name, target_path in items_to_delete:
      try:
        if os.path.isdir(target_path):
          shutil.rmtree(target_path)
          logger.info(f"Deleted data directory {item_name} from {run_dir}")
        else:
          os.remove(target_path)
          logger.info(f"Deleted data file {item_name} from {run_dir}")
      except Exception as e:
        logger.error(f"Error deleting {item_name} from {run_dir}: {e}")
        return False
    
    if not items_to_delete:
      logger.info(f"No data files to cleanup in {run_dir}")
    
    return True
    
  except Exception as e:
    logger.error(f"Error cleaning up data directory: {e}")
    return False

