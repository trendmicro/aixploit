#!/usr/bin/env python3
"""Claude command execution and streaming."""

import os
import json
import subprocess
import logging
from datetime import datetime
from typing import Optional

try:
  from dotenv import load_dotenv
except ImportError:
  load_dotenv = None

from lib.logger import get_logger
from lib.paths import get_framework_root
from lib.trace import parse_trace

logger = get_logger()

def run_claude_command(
  prompt: str,
  model: str,
  cwd: str,
  timeout_in_seconds: int = 600, # 10 minutes
  run_dir: str = None,
  mcp_config: str = None,
  display_trace: bool = True,
) -> Optional[str]:
  """Run claude command with the given prompt and stream output to file."""
  response = {
    "filepath": "",
    "status": "success"
  }

  try:
    cmd = [
      "claude",
      "--dangerously-skip-permissions",
      "--disable-slash-commands",
      "--output-format", "stream-json",
      "--verbose",
      "--model", model,
      "-p", prompt
    ]
    
    if mcp_config:
      cmd.extend([
        "--mcp-config", mcp_config
      ])

    # Generate timestamp and filename
    filename = f"trace-{model}.jsonl"
    filepath = os.path.join(run_dir, filename)
    
    # Stream output in real-time to file
    try:
      if load_dotenv:
        load_dotenv(os.path.join(get_framework_root(), ".env"))
      
      env = os.environ.copy()
      env["PYTHONUNBUFFERED"] = "1"
      # Remove Claude Code specific variables that might interfere
      claude_code_vars = [
          'CLAUDE_CODE_ENTRYPOINT', 'CLAUDE_CODE_SSE_PORT',
          'ENABLE_IDE_INTEGRATION', 'VSCODE_GIT_ASKPASS_MAIN',
          'VSCODE_GIT_ASKPASS_NODE', 'VSCODE_GIT_IPC_HANDLE'
      ]
      for var in claude_code_vars:
        env.pop(var, None)

      process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,  # Prevent stdin conflicts
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=True,  # Start in new process group
      )

      logger.debug(f"model={model}")
      #logger.debug(f"[ENVIRONMENT]\n{json.dumps(env, indent=2)}")

      with open(filepath, "w", encoding="utf-8") as trace_file:
        try:
          for line in process.stdout:
            trace_file.write(line)
            trace_file.flush()

            # Parse and display formatted output for this line
            if display_trace:
              parsed_output = parse_trace(line)
              if parsed_output:
                print(parsed_output, flush=True)
            #preview = line.rstrip("\n")[:120]
            #logger.debug(f"Streamed line ({len(line)} chars): {preview}")

          rc = process.wait(timeout=timeout_in_seconds)
        except subprocess.TimeoutExpired:
          process.kill()
          try:
            process.communicate(timeout=5)
          except Exception:
            pass
          logger.error("Claude command timed out")
          response["status"] = "Claude command timed out: current timeout is {timeout_in_seconds} seconds"
          return response

      #with open(filepath, "r", encoding="utf-8") as f:
      #  return f.read()
      logger.info(f"Successfully streamed claude output to {filepath}")
      response["filepath"] = filepath
      return response

    except Exception as e:
      logger.error(f"Error running claude command: {e}")
      response["status"] = f"Error running claude command: {e}"
      return response
  
  except Exception as e:
    logger.error(f"Unexpected error in run_claude_command: {e}")
    response["status"] = f"Unexpected error in run_claude_command: {e}"
    return response
