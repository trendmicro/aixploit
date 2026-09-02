#!/usr/bin/env python3
"""Generic orchestrator shared by every tests/{test_name}/src/main.py::test(context)."""

import os
import shutil
from typing import Any, Callable, Dict

from lib.claude_runner import run_claude_command
from lib.trace_parser import parse_trace
from lib.test_helper import resolve_placeholders
from lib.logger import get_logger

logger = get_logger()

SeedFn = Callable[[Dict[str, Any]], Dict[str, Any]]
CheckSuccessFn = Callable[[Dict[str, Any]], bool]


def run_adversarial_test(
  context: Dict[str, Any],
  seed_fn: SeedFn,
  check_success_fn: CheckSuccessFn,
  instructions_path: str,
) -> Dict[str, Any]:
  """
  Run one adversarial test end to end.

  1. seed_fn(context) writes the adversarial prompt into the target's data
     store and may return extra values to merge into context (e.g. a row id).
  2. instructions_path is read and its {placeholders} resolved against
     context, then run as the target agent's prompt.
  3. The trace is parsed and saved to execution_trace.txt in run_dir.
  4. check_success_fn(context) inspects the final data-store state for the
     exploit marker; on success the run directory is copied to exploits/.

  Args:
    context: Test context from lib/test_runner.py, plus test-specific keys
      (e.g. database_url) that seed_fn expects. Must include exploit_dir,
      run_dir, model, test_prompt.
    seed_fn: Writes adversarial content, returns extra context to merge.
    check_success_fn: Returns True if the exploit marker is present.
    instructions_path: Absolute path to the target agent's instructions file.

  Returns:
    Dict with 'status', 'execution_trace', and 'exploit_success' keys.
  """
  response = {"status": "success", "execution_trace": "", "exploit_success": False}

  extra_context = seed_fn(context)
  if extra_context:
    context.update(extra_context)

  run_dir = context["run_dir"]
  api_model = context.get("api_model", context["model"])

  with open(instructions_path, "r", encoding="utf-8") as f:
    agent_prompt = resolve_placeholders(f.read(), context)

  mcp_config = os.path.abspath(os.path.join(run_dir, ".mcp.json"))
  if not os.path.exists(mcp_config):
    logger.warning(f"MCP config not found at {mcp_config}")

  result = run_claude_command(
    prompt=agent_prompt,
    model=api_model,
    cwd=run_dir,
    timeout_in_seconds=600,
    run_dir=run_dir,
    mcp_config=mcp_config,
    display_trace=False,
  )

  if not result or result.get("status") != "success":
    response["status"] = result.get("status") if result else "Claude command failed"
    return response

  with open(result["filepath"], "r", encoding="utf-8") as f:
    jsonl_output = f.read()

  trace_result = parse_trace(agent_prompt, jsonl_output)
  if trace_result["status"] == "success":
    response["execution_trace"] = trace_result["execution_trace"]
    execution_trace_file = os.path.join(run_dir, "execution_trace.txt")
    try:
      with open(execution_trace_file, "w", encoding="utf-8") as f:
        f.write(trace_result["execution_trace"])
      logger.info(f"Saved execution trace to {execution_trace_file}")
    except Exception as e:
      logger.warning(f"Failed to save execution trace to {execution_trace_file}: {e}")

  try:
    is_successful = check_success_fn(context)
  except Exception as e:
    logger.warning(f"Failed to check exploit success: {e}")
    is_successful = False

  response["exploit_success"] = is_successful

  if is_successful:
    exploit_dir = context["exploit_dir"]
    os.makedirs(os.path.dirname(exploit_dir), exist_ok=True)
    if os.path.exists(exploit_dir):
      shutil.rmtree(exploit_dir)
    shutil.copytree(run_dir, exploit_dir)
    logger.info(f"Copied successful run directory to {exploit_dir}")

  return response
