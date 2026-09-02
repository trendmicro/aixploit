#!/usr/bin/env python3
"""Helper functions for test setup and execution."""

import os
import re
import shutil
from typing import Dict, Any

from lib.logger import get_logger
from lib.paths import tests_dir, resolve_path

logger = get_logger()


def resolve_placeholders(text: str, context: Dict[str, Any]) -> str:
  """
  Replace {placeholder} with values from context.
  
  Only processes string instances. Does not handle dict, list, tuple, or other types.
  
  Supports:
  - Simple placeholders: {key}
  - Nested placeholders: {key.subkey}
  - Escaped braces: {{ -> {
  
  Args:
    text: String with placeholders
    context: Dictionary with values to substitute
  
  Returns:
    String with placeholders replaced
  """
  if not isinstance(text, str):
    return text
  
  # Handle escaped braces first
  text = text.replace("{{", "\x00OPEN_BRACE\x00")
  text = text.replace("}}", "\x00CLOSE_BRACE\x00")
  
  # Find all placeholders - only match valid identifier-like keys (alphanumeric, underscore, dot)
  # This avoids matching JSON structure braces
  pattern = r'\{([a-zA-Z_][a-zA-Z0-9_.]*)\}'
  
  def replace_placeholder(match):
    key = match.group(1)
    # Support nested keys (e.g., "key.subkey")
    value = context
    for part in key.split('.'):
      if not isinstance(value, dict):
        return match.group(0)  # Return original if not a dict
      if part not in value:
        return match.group(0)  # Return original if key doesn't exist
      value = value[part]
    
    # Convert to string
    return str(value)
  
  result = re.sub(pattern, replace_placeholder, text)
  
  # Restore escaped braces
  result = result.replace("\x00OPEN_BRACE\x00", "{")
  result = result.replace("\x00CLOSE_BRACE\x00", "}")
  
  return result

def copy_template(context: Dict[str, Any]) -> bool:
  """
  Copy all template files from setup/templates with placeholder replacement.
  
  Args:
    context: Context for placeholder resolution
    
  Returns:
    True if successful, False otherwise
  """
  test_name = context["test_name"]
  run_dir = context["run_dir"]
  
  # Get templates directory: tests/{test_name}/setup/templates/
  templates_dir = os.path.join(tests_dir(), test_name, "setup", "templates")
  
  if not os.path.exists(templates_dir):
    logger.error(f"Templates directory not found: {templates_dir}")
    return False
  
  if not os.path.isdir(templates_dir):
    logger.error(f"Templates path is not a directory: {templates_dir}")
    return False
  
  # Process all files in templates directory
  try:
    template_files = [f for f in os.listdir(templates_dir)]
    if not template_files:
      logger.warning(f"No template files found in {templates_dir}")
      return True  # Not an error, just no templates to copy
    
    for filename in template_files:
      source_path = os.path.join(templates_dir, filename)
      # Skip directories
      if os.path.isdir(source_path):
        continue
      
      # Read template file
      try:
        with open(source_path, 'r', encoding='utf-8') as f:
          content = f.read()
      except Exception as e:
        logger.error(f"Error reading template file {source_path}: {e}")
        return False
      
      # Replace all placeholders in template content
      content = resolve_placeholders(content, context)
      
      # Write to target (same filename in run_dir)
      target_path = os.path.join(run_dir, filename)
      try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
          f.write(content)
        logger.info(f"Copied template {filename} to {target_path}")
      except Exception as e:
        logger.error(f"Error writing template file {target_path}: {e}")
        return False
    
    return True
    
  except Exception as e:
    logger.error(f"Error processing templates: {e}")
    return False

def copy_data_directory(context: Dict[str, Any]) -> bool:
  """
  Copy all files from tests/{test_name}/setup/data/ to run directory.
  
  Args:
    context: Context for placeholder resolution (unused, kept for compatibility)
    
  Returns:
    True if successful, False otherwise
  """
  test_name = context["test_name"]
  run_dir = context["run_dir"]
  
  # Get data directory: tests/{test_name}/setup/data/
  data_dir = os.path.join(tests_dir(), test_name, "setup", "data")
  
  if not os.path.exists(data_dir):
    logger.warning(f"Data directory not found: {data_dir}")
    return True  # Not an error, just no data to copy
  
  if not os.path.isdir(data_dir):
    logger.error(f"Data path is not a directory: {data_dir}")
    return False
  
  try:
    # Copy all files and directories recursively to run_dir
    # Use copytree with dirs_exist_ok=True to handle existing directories
    for item_name in os.listdir(data_dir):
      source_path = os.path.join(data_dir, item_name)
      target_path = os.path.join(run_dir, item_name)
      
      if os.path.isdir(source_path):
        # Copy directory tree
        if os.path.exists(target_path):
          shutil.rmtree(target_path)
        shutil.copytree(source_path, target_path)
        logger.info(f"Copied data directory {item_name} to {target_path}")
      else:
        # Copy file
        shutil.copy2(source_path, target_path)
        logger.info(f"Copied data file {item_name} to {target_path}")
    
    return True
    
  except Exception as e:
    logger.error(f"Error copying data directory: {e}")
    return False

