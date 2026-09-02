#!/usr/bin/env python3
"""Configuration loading module for blackbox tests."""

import os
import sys
from typing import Dict, Any, Optional

try:
  import yaml
except ImportError:
  yaml = None

from lib.paths import get_framework_root
from lib.logger import get_logger

logger = get_logger()


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
  """Load configuration from YAML file.
  
  Args:
    config_path: Path to config file. If None, uses default location.
    
  Returns:
    Dictionary containing configuration values.
    
  Raises:
    SystemExit: If config file not found or PyYAML not available.
  """
  if config_path is None:
    # Use paths module for consistent path handling
    framework_root = get_framework_root()
    config_path = os.path.join(framework_root, "aixploit.yaml")
  
  if not os.path.exists(config_path):
    logger.error(f"Configuration file not found: {config_path}")
    sys.exit(1)
  
  if yaml is None:
    logger.error("PyYAML is required to load configuration. Please install it: pip install pyyaml")
    sys.exit(1)
  
  with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
  
  return config


def validate_config(config: Dict[str, Any]) -> None:
  """Validate that required configuration values are present.
  
  Args:
    config: Configuration dictionary.
    
  Raises:
    SystemExit: If required values are missing.
  """
  prompts_filepath = config.get("prompts_filepath")
  models = config.get("models", [])
  
  if not prompts_filepath:
    logger.error("prompts_filepath must be specified in config file")
    sys.exit(1)
  
  if not models:
    logger.error("models list must be specified in config file")
    sys.exit(1)


