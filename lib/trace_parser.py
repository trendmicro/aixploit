#!/usr/bin/env python3
"""Parser for claude's stream-json output."""

import json
from typing import Dict, Any, List
from lib.logger import get_logger

logger = get_logger()

_EMPTY_TEXT = {"", "(no content)"}


def _format_content_items(items: List[Any]) -> List[str]:
  """Format message content items into trace lines. Skips empty / placeholder text."""
  parts: List[str] = []
  for item in items:
    if not isinstance(item, dict):
      continue

    item_type = item.get("type")

    if item_type == "text":
      text = (item.get("text") or "").strip()
      if text and text not in _EMPTY_TEXT:
        parts.append(text)

    elif item_type == "tool_use":
      if "name" in item:
        parts.append(f"tool_use: {item['name']}")
      if "input" in item:
        parts.append(f"tool_input:\n{json.dumps(item['input'])}")

    elif item_type == "tool_result":
      content = item.get("content")
      if isinstance(content, list):
        for subitem in content:
          if isinstance(subitem, dict) and subitem.get("type") == "text":
            text = subitem.get("text")
            if text is not None and str(text).strip() not in _EMPTY_TEXT:
              parts.append(f"tool_result:\n{text}")
      elif isinstance(content, str) and content.strip() not in _EMPTY_TEXT:
        parts.append(f"tool_result:\n{content}")

    elif item_type in ("thinking", "redacted_thinking"):
      thinking_text = item.get("thinking") or item.get("text")
      if thinking_text and str(thinking_text).strip() not in _EMPTY_TEXT:
        parts.append(f"thinking:\n{thinking_text}")

    else:
      raise ValueError(f"Unsupported content item type: {item_type}")

  return parts


def _system_metadata_lines(data: Dict[str, Any]) -> List[str]:
  """Extract non-empty system init metadata lines."""
  lines: List[str] = []
  if "claude_code_version" in data:
    lines.append(f"claude_code_version: {data['claude_code_version']}")
  if "cwd" in data:
    lines.append(f"cwd: {data['cwd']}")
  if "tools" in data:
    lines.append(f"tools: {json.dumps(data['tools'])}")
  if "mcp_servers" in data:
    lines.append(f"mcp_servers: {json.dumps(data['mcp_servers'])}")
  if "model" in data:
    lines.append(f"model: {data['model']}")
  if "skills" in data:
    lines.append(f"skills: {json.dumps(data['skills'])}")
  return lines


def parse_trace(user_prompt: str, jsonl_output: str) -> Dict[str, Any]:
  """Parse trace from claude's stream-json output and extract key information."""
  response = {
    "execution_trace": "",
    "status": "success",
  }

  try:
    system_parts: List[str] = []
    conversation_parts: List[str] = []
    user_prompt_injected = False

    for line in jsonl_output.strip().split("\n"):
      if not line.strip():
        continue

      try:
        data = json.loads(line)
        data_type = data.get("type")

        # Claude Code emits many system events (e.g. subtype=thinking_tokens);
        # only init carries session metadata. Inject the agent prompt once.
        if data_type == "system":
          subtype = data.get("subtype")
          if subtype not in (None, "init"):
            continue

          meta = _system_metadata_lines(data)
          if meta:
            system_parts.append("\n[system]")
            system_parts.extend(meta)

          if user_prompt and not user_prompt_injected:
            conversation_parts.append(f"\n[user]\n{user_prompt}")
            user_prompt_injected = True

        elif data_type in ("assistant", "user"):
          message = data.get("message")
          if not isinstance(message, dict):
            continue

          content = message.get("content")
          body = _format_content_items(content) if isinstance(content, list) else []
          if not body:
            continue

          role = message.get("role") or data_type
          conversation_parts.append(f"\n[{role}]")
          conversation_parts.extend(body)

        elif data_type == "result":
          # Repeat of the last conversation message; skip.
          pass

        else:
          raise ValueError(f"Unsupported data type: {data_type}")

      except json.JSONDecodeError:
        continue
      except ValueError:
        raise

    system = "\n".join(system_parts) if system_parts else ""
    conversation = "\n".join(conversation_parts) if conversation_parts else ""
    if system and conversation:
      response["execution_trace"] = f"{system}\n{conversation}"
    elif system:
      response["execution_trace"] = system
    elif conversation:
      response["execution_trace"] = conversation
    else:
      response["execution_trace"] = jsonl_output

    return response

  except Exception as e:
    response["status"] = f"Failed to parse trace: {e}"
    logger.error(f"Failed to parse trace: {e}")
    return response
