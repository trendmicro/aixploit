#!/usr/bin/env python3
"""Test runner module for executing individual blackbox tests."""

import os
import runpy
import sys
import json
from typing import Dict, Any

# Add automation directory to Python path so we can import modules
lib_dir = os.path.dirname(os.path.abspath(__file__))
automation_dir = os.path.dirname(lib_dir)
if automation_dir not in sys.path:
  sys.path.insert(0, automation_dir)

from lib.logger import get_logger

from lib.paths import runs_dir, exploits_dir, get_framework_root
from lib.file_ops import cleanup_data_directory
from lib.docker_ops import (
  COMPOSE_FILES,
  remove_stale_mcp_containers,
  start_docker_containers,
  stop_docker_containers
)
from lib.test_helper import copy_template, copy_data_directory

logger = get_logger()


def run_test(
  test_name: str,
  model: str,
  api_model: str,
  runs: str,
  exploits: str,
  test_id: str,
  test_prompt: str,
  host_port: int
):
  """
  Run a single test using configuration-driven approach.
  
  Args:
    test_name: Name of the test (directory under test/)
    model: Directory-safe model slug for paths and containers
    api_model: Model name passed to the Claude CLI
    runs: Runs directory name
    exploits: Exploits directory name
    test_id: Prompt ID from prompts.jsonl
    test_prompt: The adversarial prompt
    host_port: PostgreSQL port
  
  Returns:
    The return value from the test module's test(context) function.
  """
  # Build run directory path
  run_dir = runs_dir(runs, test_name, model, test_id)
  exploit_dir = exploits_dir(exploits, test_name, model, test_id)

  # Skip test if execution_trace.txt already exists in run directory
  trace_file = os.path.join(run_dir, "execution_trace.txt")
  if os.path.isfile(trace_file):
    return None

  # Create run directory
  os.makedirs(run_dir, exist_ok=True)
  
  logger.info(f"Starting test id={test_id} with test: {test_name}")
  
  containers_started = False
  
  try:    
    context = {
      "test_name": test_name,
      "test_id": test_id,
      "test_prompt": test_prompt,
      "host_port": host_port,
      "run_dir": os.path.abspath(run_dir),
      "exploit_dir": os.path.abspath(exploit_dir),
      "model": model,
      "api_model": api_model,
      "runs": runs,
      "framework_root": get_framework_root()
    }
    
    # Setup: Copy templates, data directories, create docker-compose.yml
    logger.info(f"Setting up test {test_id}")
    try:
      # Copy files from setup/templates to run dir.
      if not copy_template(context):
        logger.error(f"Test setup failed for test {test_id}: Failed to copy templates [{test_name}]")
        return False
      
      # Copy data directories from config
      if not copy_data_directory(context):
        logger.error(f"Test setup failed for test {test_id}: Failed to copy data directory [{test_name}]")
        return False
    except Exception as e:
      logger.error(f"Error in setup for test {test_id}: {e}")
      return False
    
    # Start docker containers (compose waits for running/healthy via --wait).
    # Always mark for cleanup once templates exist so a failed `compose up`
    # still tears down this run's uniquely named resources, not a sibling's.
    has_compose = any(os.path.isfile(os.path.join(run_dir, f)) for f in COMPOSE_FILES)
    has_mcp = os.path.exists(os.path.join(run_dir, ".mcp.json"))
    containers_started = has_compose or has_mcp
    if has_mcp:
      remove_stale_mcp_containers(run_dir)
    if has_compose and not start_docker_containers(run_dir):
      logger.error(f"Test {test_id} failed to start docker containers")
      return False

    # Run test via tests.{test_name}.src.main.test(context)
    module_name = f"tests.{test_name}.src.main"
    mod_globals = runpy.run_module(module_name, run_name=module_name)
    if "test" not in mod_globals:
      logger.error(f"Module {module_name} has no 'test' function")
      return False
    test_func = mod_globals["test"]
    result = test_func(context)
    logger.info(f"Completed test {test_id}")
    return result
    
  except Exception as e:
    logger.error(f"Error running test {test_id}: {e}")
    import traceback
    logger.error(traceback.format_exc())
    return False
    
  finally:
    # Always cleanup containers
    if containers_started:
      logger.info(f"Cleaning up containers for test {test_id}")
      stop_docker_containers(test_name, test_id, model, runs)
    
    # Cleanup data directories (context may not be defined if error occurred early)
    #
    #try:
    #  cleanup_data_directory(test_name, context, run_dir)
    #  except Exception as e:
    #    logger.warning(f"Error during data directory cleanup: {e}")
