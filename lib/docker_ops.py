#!/usr/bin/env python3
"""Docker operations module for blackbox tests."""

import json
import os
import subprocess
from typing import List, Optional

try:
  import yaml
except ImportError:
  yaml = None

from lib.logger import get_logger

logger = get_logger()

COMPOSE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def _has_compose_file(run_dir: str) -> bool:
  """Return True if run_dir contains a docker compose config file."""
  return any(os.path.isfile(os.path.join(run_dir, f)) for f in COMPOSE_FILES)


def start_docker_containers(run_dir: str, wait_timeout: int = 120) -> bool:
  """
  Start docker containers using docker compose and wait until they are ready.

  Uses `docker compose up -d --wait` so Compose waits for services to be running.
  If a service defines a healthcheck in docker-compose.yml, Compose waits for it
  to become healthy. Tests that need a ready service (e.g. postgres) should add
  a healthcheck to their compose file; the runner stays generic.
  """
  try:
    if not _has_compose_file(run_dir):
      logger.info(f"No docker compose config found in {run_dir} (looked for {COMPOSE_FILES})")
      return False

    result = subprocess.run(
      ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", str(wait_timeout)],
      cwd=run_dir,
      capture_output=True,
      text=True,
      check=True
    )
    logger.info(f"Docker containers started: {result.stdout}")
    return True
  except subprocess.CalledProcessError as e:
    logger.error(f"Failed to start docker containers: {e.stderr}")
    return False


def get_compose_project_name(run_dir: str) -> Optional[str]:
  """Extract project name from docker-compose.yml file."""
  compose_file = os.path.join(run_dir, "docker-compose.yml")
  if not os.path.exists(compose_file):
    return None
  
  if yaml is None:
    logger.warning("PyYAML not available, cannot parse docker-compose.yml")
    return None
  
  try:
    with open(compose_file, 'r', encoding='utf-8') as f:
      compose_data = yaml.safe_load(f)
      if isinstance(compose_data, dict) and 'name' in compose_data:
        return compose_data['name']
  except Exception as e:
    logger.warning(f"Error parsing docker-compose.yml: {e}")
  
  return None


def remove_stale_mcp_containers(run_dir: str) -> None:
  """
  Force-remove named MCP containers from a previous crashed run.

  Claude starts these via `docker run --name ...`. If a leftover container
  still holds that name, the next `docker run` fails and MCP status is
  reported as failed.
  """
  for container_name in _container_names_from_mcp_json(run_dir):
    logger.info(f"Removing stale MCP container if present: {container_name}")
    subprocess.run(
      ["docker", "rm", "-f", container_name],
      capture_output=True,
      text=True,
      check=False,
    )


def _container_names_from_mcp_json(run_dir: str) -> List[str]:
  """
  Parse .mcp.json in run_dir and return container names from docker run --name ...
  (Containers started by Claude/code via MCP config, not by compose.)
  """
  mcp_path = os.path.join(run_dir, ".mcp.json")
  if not os.path.isfile(mcp_path):
    return []
  try:
    with open(mcp_path, "r", encoding="utf-8") as f:
      data = json.load(f)
  except (json.JSONDecodeError, OSError) as e:
    logger.warning(f"Could not read .mcp.json in {run_dir}: {e}")
    return []
  names = []
  servers = data.get("mcpServers") or {}
  for server_cfg in servers.values():
    if not isinstance(server_cfg, dict):
      continue
    args = server_cfg.get("args") or []
    if not isinstance(args, list):
      continue
    for i, arg in enumerate(args):
      if arg == "--name" and i + 1 < len(args):
        names.append(args[i + 1])
        break
  return names


def stop_docker_containers(test_name: str, test_id: str, model: str, runs_root: str) -> bool:
  """
  Stop and remove containers started for this run:
  1. Compose project (from docker-compose in run_dir, name from get_compose_project_name).
  2. Containers started via .mcp.json (docker run --name ... from Claude/code).
  """
  try:
    from lib.paths import runs_dir
    run_dir = runs_dir(runs_root, test_name, model, test_id)
    
    if not os.path.exists(run_dir):
      logger.error(f"Run directory does not exist: {run_dir}")
      return False
    
    # 1. Stop compose project (all containers from docker-compose)
    project_name = get_compose_project_name(run_dir)
    if project_name:
      logger.info(f"Stopping compose project: {project_name}")
      result = subprocess.run(
        ["docker", "compose", "-p", project_name, "down", "-v"],
        cwd=run_dir,
        capture_output=True,
        text=True,
        check=False
      )
      if result.returncode == 0:
        logger.info(f"Compose project stopped: {project_name}")
      else:
        logger.info(f"Compose down finished with code {result.returncode}: {result.stderr or result.stdout}")
    else:
      logger.info("Stopping compose (default project in run_dir)")
      result = subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=run_dir,
        capture_output=True,
        text=True,
        check=False
      )
      if result.returncode == 0:
        logger.info("Compose (default project) stopped")
      else:
        logger.info(f"Compose down finished with code {result.returncode}: {result.stderr or result.stdout}")

    # 2. Stop containers started via .mcp.json (docker run --name ...)
    mcp_container_names = _container_names_from_mcp_json(run_dir)
    for container_name in mcp_container_names:
      logger.info(f"Stopping container: {container_name}")
      subprocess.run(
        ["docker", "stop", container_name],
        capture_output=True,
        text=True,
        check=False
      )
      logger.info(f"Removing container: {container_name}")
      subprocess.run(
        ["docker", "rm", container_name],
        capture_output=True,
        text=True,
        check=False
      )
    
    logger.info(f"Stopped and removed containers for test {test_id}")
    return True
  except Exception as e:
    logger.error(f"Error stopping containers: {e}")
    return False

