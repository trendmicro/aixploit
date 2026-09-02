#!/usr/bin/env python3
"""Logging utilities for the framework."""

import logging
import os

from lib.paths import get_framework_root


def get_logger(name: str = "aixploit"):
  """
  Get the logger for the current run.
  
  Returns:
    Logger instance configured to write to blackbox.log in framework root
  """
  framework_root = get_framework_root()
  log_file = os.path.join(framework_root, f"{name}.log")
  
  logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    filename=log_file,
    filemode="a",
  )
  return logging.getLogger('blackbox')

