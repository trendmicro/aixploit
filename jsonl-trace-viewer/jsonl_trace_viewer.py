#!/usr/bin/env python3
"""
jsonl_trace_viewer.py — Render a Claude Code headless (--output-format
stream-json) .jsonl log as a modern, color-coded terminal view.

Usage:
  python3 jsonl_trace_viewer.py trace.jsonl
  python3 jsonl_trace_viewer.py trace.jsonl --no-truncate
"""

import argparse
import json
import sys

from rich.console import Console, Group
from rich.padding import Padding
from rich.syntax import Syntax
from rich.text import Text
from rich.table import Table

MAX_CHARS = 1400

# Flat, modern palette (Tailwind-ish)
C = {
  "system": "#8b5cf6",     # violet
  "user": "#0ea5e9",       # sky
  "assistant": "#10b981",  # emerald
  "tool": "#f59e0b",       # amber
  "result": "#64748b",     # slate
  "error": "#ef4444",      # red
  "summary": "#3b82f6",    # blue
  "dim": "#475569",
}

INDENT = (0, 0, 0, 3)  # top, right, bottom, left


def clip(text, truncate):
  if truncate and len(text) > MAX_CHARS:
    return text[:MAX_CHARS] + f"\n[dim]… {len(text) - MAX_CHARS} more chars (--no-truncate to show all)[/dim]"
  return text


def section(console, icon, label, color):
  """Top-only divider line — no side/bottom borders. One blank line separates
  this from the previous message; nothing separates the line from its content."""
  console.print()
  console.rule(f"[bold {color}]{icon} {label}[/bold {color}]", style=color, align="left")


def show(console, renderable):
  console.print(Padding(renderable, INDENT))


def render_tool_result_content(content):
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts = []
    for block in content:
      if isinstance(block, dict) and block.get("type") == "text":
        parts.append(block.get("text", ""))
      else:
        parts.append(json.dumps(block, ensure_ascii=False))
    return "\n".join(parts)
  return json.dumps(content, ensure_ascii=False)


def render_system(console, event):
  table = Table(show_header=False, box=None, padding=(0, 1, 0, 0), expand=False)
  table.add_column(style=f"bold {C['dim']}")
  table.add_column()
  rows = [
    ("model", event.get("model")),
    ("version", event.get("claude_code_version")),
    ("cwd", event.get("cwd")),
    ("permissions", event.get("permissionMode")),
  ]
  if event.get("mcp_servers"):
    rows.append(("mcp", ", ".join(f"{s['name']} ({s['status']})" for s in event["mcp_servers"])))
  if event.get("skills"):
    rows.append(("skills", ", ".join(event["skills"])))
  if event.get("tools"):
    tools = event["tools"]
    shown = ", ".join(tools[:8]) + (f" … +{len(tools) - 8} more" if len(tools) > 8 else "")
    rows.append(("tools", shown))
  for k, v in rows:
    if v:
      table.add_row(k, str(v))
  section(console, "◆", "SESSION START", C["system"])
  show(console, table)


def render_assistant_turn(console, blocks, truncate):
  """Render one assistant message (may contain text + tool_use blocks)."""
  text_parts = []
  tool_calls = []
  for block in blocks:
    btype = block.get("type")
    if btype == "text" and block.get("text", "").strip():
      text_parts.append(Text(clip(block["text"], truncate)))
    elif btype == "thinking":
      text_parts.append(Text(clip(block.get("thinking", ""), truncate), style=f"italic {C['dim']}"))
    elif btype == "tool_use":
      tool_calls.append(block)

  if not text_parts and not tool_calls:
    return

  section(console, "●", "assistant", C["assistant"])
  if text_parts:
    show(console, Group(*text_parts))
  for tc in tool_calls:
    name = tc.get("name", "?")
    payload = json.dumps(tc.get("input", {}), indent=2, ensure_ascii=False)
    payload = clip(payload, truncate)
    show(console, Text(f"⚙ {name}", style=f"bold {C['tool']}"))
    show(console, Syntax(payload, "json", theme="dracula", word_wrap=True, background_color="default"))


def render_user_turn(console, blocks, truncate):
  for block in blocks:
    if block.get("type") == "tool_result":
      text = render_tool_result_content(block.get("content"))
      is_error = block.get("is_error", False)
      text = clip(text, truncate)
      pretty = None
      try:
        pretty = json.dumps(json.loads(text.replace("'", '"')), indent=2, ensure_ascii=False)
      except Exception:
        pretty = None
      color = C["error"] if is_error else C["result"]
      icon = "✕" if is_error else "↩"
      label = "tool error" if is_error else "tool result"
      body = Syntax(pretty, "json", theme="dracula", word_wrap=True, background_color="default") if pretty else Text(text)
      section(console, icon, label, color)
      show(console, body)
    elif block.get("type") == "text" and block.get("text", "").strip():
      text = clip(block["text"], truncate)
      section(console, "○", "user", C["user"])
      show(console, Text(text))


def render_result(console, event):
  table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
  table.add_column(style=f"bold {C['dim']}")
  table.add_column()
  status = "[bold red]✕ error[/bold red]" if event.get("is_error") else "[bold green]✓ success[/bold green]"
  table.add_row("status", status)
  table.add_row("turns", str(event.get("num_turns")))
  table.add_row("duration", f"{event.get('duration_ms')} ms  (api {event.get('duration_api_ms')} ms)")
  table.add_row("cost", f"${event.get('total_cost_usd', 0):.4f}")
  section(console, "▣", "RUN SUMMARY", C["summary"])
  show(console, table)
  if event.get("result"):
    section(console, "»", "final response", C["summary"])
    show(console, Text(str(event["result"])))


def main():
  parser = argparse.ArgumentParser(description="View a Claude Code headless JSONL trace, modern style.")
  parser.add_argument("file", help="Path to the .jsonl trace file")
  parser.add_argument("--no-truncate", action="store_true", help="Show full content, no length limit")
  args = parser.parse_args()
  truncate = not args.no_truncate

  console = Console()
  console.rule(f"[bold]{args.file}[/bold]", style=C["dim"])

  turn_num = 0
  with open(args.file, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      event = json.loads(line)
      etype = event.get("type")

      if etype == "system":
        render_system(console, event)
      elif etype == "assistant":
        turn_num += 1
        render_assistant_turn(console, event["message"].get("content", []), truncate)
      elif etype == "user":
        render_user_turn(console, event["message"].get("content", []), truncate)
      elif etype == "result":
        render_result(console, event)

  console.rule(f"[bold]{turn_num} assistant turns[/bold]", style=C["dim"])


if __name__ == "__main__":
  sys.exit(main())
