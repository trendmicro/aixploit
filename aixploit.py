#!/usr/bin/env python3
"""Blackbox test runner that executes tests for each prompt."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

# Add automation directory to Python path so we can import test modules
import os
automation_dir = os.path.dirname(os.path.abspath(__file__))
if automation_dir not in sys.path:
  sys.path.insert(0, automation_dir)

log_path = os.path.join(automation_dir, "aixploit.log")
if os.path.exists(log_path):
  os.remove(log_path)

from lib.logger import get_logger

from lib.config import load_config, validate_config
from lib.models import ModelSpec, parse_models
from lib.file_ops import construct_prompts
from lib.heatmap import save_exploit_heatmap
from lib.paths import exploits_dir, resolve_path, runs_dir
from lib.run_display import RunDisplay
from lib.test_runner import run_test
from typing import Callable, Optional, TypeVar, Iterable

logger = get_logger()

T = TypeVar("T")

def parse_args():
  """Parse command line arguments."""
  parser = argparse.ArgumentParser(description="Run blackbox tests")

  parser.add_argument(
    "--cfg",
    type=str,
    default='aixploit.yaml',
    help="Cfg filepath (e.g. aixploit.yaml)"
  )

  #parser.add_argument(
  #  "model",
  #  type=str,
  #  help="Model name to use for testing"
  #)
  return parser.parse_args()

def _run_model_wrapper(pair):
    """Thin wrapper for run_model, needed only for run_parallel dispatch."""
    return run_model(*pair)


def _has_execution_trace(runs: str, test_name: str, model: str, test_id) -> bool:
  """True if this run folder already has execution_trace.txt."""
  trace_file = os.path.join(runs_dir(runs, test_name, model, test_id), "execution_trace.txt")
  return os.path.isfile(trace_file)


def _has_exploit(exploits: str, test_name: str, model: str, test_id) -> bool:
  """True if this sample already has a confirmed-exploit archive."""
  return os.path.isdir(exploits_dir(exploits, test_name, model, test_id))

def run_parallel(items: Iterable[T], fn: Callable[[T], None], max_workers: int) -> None:
    """Run fn on each item — sequentially if max_workers <= 1, else threaded."""
    if max_workers <= 1:
        for item in items:
            fn(item)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(fn, item): item for item in items}
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Task {futures[future]} raised exception: {e}")

def run_model(
    model_index: int,
    model: ModelSpec,
    test_name: str,
    prompts: list,
    max_workers: int,
    runs: str,
    exploits: str,
    test_host_port: int,
    display: Optional[RunDisplay] = None,
) -> None:
    """Run all prompts for a single model."""
    logger.info(
        f"Starting blackbox tests with model: {model.api} "
        f"(dir={model.dir}) and {max_workers} workers"
    )
    base_port = test_host_port + model_index * len(prompts)

    pending = []
    host_port = base_port
    for prompt in prompts:
        test_id = prompt['id']
        if _has_execution_trace(runs, test_name, model.dir, test_id):
            if display is not None:
                display.record_skip(
                    model.display,
                    test_id,
                    _has_exploit(exploits, test_name, model.dir, test_id),
                )
        else:
            pending.append((prompt, host_port))
        host_port += 1

    if not pending:
        logger.info(f"All tests skipped for model: {model.display}")
        return

    def _execute(prompt, host_port):
        test_id = prompt["id"]
        if display is not None:
            display.record_start(model.display, test_id)
        try:
            result = run_test(
                test_name,
                model.dir,
                model.api,
                runs,
                exploits,
                test_id,
                prompt["prompt"],
                host_port,
            )
        except Exception as e:
            if display is not None:
                display.record_error(model.display, test_id, str(e))
            raise
        if display is not None:
            display.record_result(model.display, test_id, result)
        return result

    if max_workers <= 1:
        for prompt, host_port in pending:
            try:
                result = _execute(prompt, host_port)
                if result is None:
                    logger.info(f"[{model.display}] Test {prompt['id']} skipped")
                elif result:
                    logger.info(f"[{model.display}] Test {prompt['id']} completed successfully")
                else:
                    logger.error(f"[{model.display}] Test {prompt['id']} failed")
            except Exception as e:
                logger.error(f"[{model.display}] Test {prompt['id']} raised exception: {e}")
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for prompt, host_port in pending:
                future = executor.submit(_execute, prompt, host_port)
                futures.append((future, prompt['id']))
            for future, prompt_id in futures:
                try:
                    result = future.result()
                    if result is None:
                        logger.info(f"[{model.display}] Test {prompt_id} skipped")
                    elif result:
                        logger.info(f"[{model.display}] Test {prompt_id} completed successfully")
                    else:
                        logger.error(f"[{model.display}] Test {prompt_id} failed")
                except Exception as e:
                    logger.error(f"[{model.display}] Test {prompt_id} raised exception: {e}")

    logger.info(f"All tests completed for model: {model.display}")


def main():
  """Main entry point."""
  args = parse_args()

  # Prompt for config file if not provided
  if args.cfg is None:
    args.cfg = input("Enter config file path (default: aixploit.yaml): ").strip()
    if not args.cfg:
      args.cfg = "aixploit.yaml"

  # Load and validate configuration
  cfg = load_config(args.cfg)
  validate_config(cfg)

  test_name = cfg["test_name"]
  max_workers = cfg["max_workers"]
  model_specs = parse_models(cfg["models"])
  runs = resolve_path(cfg["runs"])
  exploits = resolve_path(cfg["exploits"])
  heatmap_dir = resolve_path(cfg.get("heatmap", "./results/heatmap"))
  test_host_port = cfg["test_host_port"]
  top_k = cfg["top_k"]
  prompts_filepath = cfg["prompts_filepath"]

  # Construct tests list
  prompts = construct_prompts(prompts_filepath)
  logger.info(f"Found {len(prompts)} tests to run")

  if not prompts:
    logger.error("No prompts found. Exiting.")
    sys.exit(1)

  # Run each test in parallel
  """ Models not working with Claude Code
  gpt-4o: 1K trace file. It hangs.
  gpt-5-codex: It hangs.
  gpt-oss-120b: It hangs.
  deepseek-r1: It doesn't implement tool calls. Just reasoning.
  deepseek-v3.1: Tool call errors.
  """
  prompts = prompts[:top_k]

  display = RunDisplay(
    test_name=test_name,
    models=[spec.display for spec in model_specs],
    n_prompts=len(prompts),
    max_workers=max_workers,
  )
  with display:
    if max_workers <= 1:
      for model_index, model in enumerate(model_specs):
          run_model(
              model_index, model, test_name, prompts, max_workers,
              runs, exploits, test_host_port, display,
          )
    else:
      run_parallel(
          [
              (i, m, test_name, prompts, max_workers, runs, exploits, test_host_port, display)
              for i, m in enumerate(model_specs)
          ],
          _run_model_wrapper,
          max_workers,
      )

    heatmap_path = save_exploit_heatmap(test_name, runs, exploits, heatmap_dir)
    if heatmap_path:
      display.set_heatmap_path(heatmap_path)

  logger.info("All tests completed")


if __name__ == "__main__":
  main()
