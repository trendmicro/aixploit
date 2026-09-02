#!/usr/bin/env python3
"""Parser for a single claude stream-json line (live display)."""

import json
from typing import Optional

from lib.logger import get_logger
from lib.trace_parser import _format_content_items, _system_metadata_lines

logger = get_logger()


def parse_trace(jsonl_line: str) -> Optional[str]:
  """Parse a single jsonl line from claude's stream-json output and return formatted output."""
  if not jsonl_line.strip():
    return None

  try:
    data = json.loads(jsonl_line)
    data_type = data.get("type")
    output_parts = []

    if data_type == "system":
      subtype = data.get("subtype")
      if subtype not in (None, "init"):
        return None

      meta = _system_metadata_lines(data)
      if not meta:
        return None
      output_parts.append("\n[system]")
      output_parts.extend(meta)

    elif data_type in ("assistant", "user"):
      message = data.get("message")
      if not isinstance(message, dict):
        return None

      content = message.get("content")
      body = _format_content_items(content) if isinstance(content, list) else []
      if not body:
        return None

      role = message.get("role") or data_type
      output_parts.append(f"\n[{role}]")
      output_parts.extend(body)

    elif data_type == "result":
      return None

    else:
      raise ValueError(f"Unsupported data type: {data_type}")

    if output_parts:
      return "\n".join(output_parts)
    return None

  except json.JSONDecodeError:
    return None
  except ValueError as e:
    logger.error(f"Failed to parse trace line: {e}")
    return None
  except Exception as e:
    logger.error(f"Unexpected error parsing trace line: {e}")
    return None
