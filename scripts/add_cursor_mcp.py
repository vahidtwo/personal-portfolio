#!/usr/bin/env python3
"""Merge the my-inventory MCP server into Cursor's mcp.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER_NAME = "my-inventory"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add the my-inventory MCP server to Cursor (merges ~/.cursor/mcp.json).",
    )
    parser.add_argument("--token", required=True, help="Bearer token from the profile page")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000/mcp",
        help="Streamable HTTP endpoint (default: http://127.0.0.1:8000/mcp)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".cursor" / "mcp.json",
        help="Cursor MCP config path (default: ~/.cursor/mcp.json)",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must be a JSON object")
    return data


def main() -> int:
    args = parse_args()
    token = args.token.strip()
    if not token:
        raise SystemExit("--token is empty")
    url = args.url.strip()
    if not url:
        raise SystemExit("--url is empty")

    path = args.config.expanduser()
    data = load_config(path)
    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
        data["mcpServers"] = servers
    if not isinstance(servers, dict):
        raise SystemExit(f"{path} mcpServers must be a JSON object")

    servers[SERVER_NAME] = {
        "url": url,
        "headers": {"Authorization": f"Bearer {token}"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {SERVER_NAME} to {path}")
    print("Reload MCP in Cursor: Settings → MCP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
