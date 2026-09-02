#!/usr/bin/env python3
"""Delete all Docker containers whose name starts with 'mcp-sqlite'."""

import subprocess
import sys


def main() -> int:
  result = subprocess.run(
    ["docker", "ps", "-a", "--format", "{{.Names}}"],
    capture_output=True,
    text=True,
    check=False,
  )
  if result.returncode != 0:
    print(result.stderr or result.stdout or "Failed to list containers", file=sys.stderr)
    return 1

  names = (n.strip() for n in (result.stdout or "").splitlines() if n.strip())
  to_remove = [n for n in names if n.startswith("mcp-sqlite")]

  if not to_remove:
    return 0

  for name in to_remove:
    subprocess.run(
      ["docker", "rm", "-f", name],
      capture_output=True,
      text=True,
      check=False,
    )

  return 0


if __name__ == "__main__":
  sys.exit(main())
