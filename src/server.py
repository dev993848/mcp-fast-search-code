import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

server = Server("space-ngrams")


def run_ripgrep(pattern: str, path: str, file_glob: str | None = None, context_lines: int = 2) -> str:
    """Run ripgrep and return formatted results."""
    cmd = [
        "rg",
        "--json",
        "--max-count", "50",
        "--context", str(context_lines),
    ]
    if file_glob:
        cmd += ["--glob", file_glob]
    cmd += [pattern, path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        return "Error: ripgrep (rg) not found. Install it: https://github.com/BurntSushi/ripgrep#installation"
    except subprocess.TimeoutExpired:
        return "Error: search timed out after 15 seconds"

    if result.returncode not in (0, 1):
        return f"Error: {result.stderr.strip()}"

    matches = []
    current_file = None
    lines_buf = []

    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = data.get("type")
        if kind == "begin":
            current_file = data["data"]["path"]["text"]
            lines_buf = []
        elif kind in ("context", "match"):
            line_no = data["data"]["line_number"]
            text = data["data"]["lines"]["text"].rstrip()
            prefix = ">" if kind == "match" else " "
            lines_buf.append(f"  {prefix} {line_no:5}: {text}")
        elif kind == "end":
            if current_file and lines_buf:
                matches.append(f"{current_file}\n" + "\n".join(lines_buf))
            current_file = None
            lines_buf = []

    if not matches:
        return "No matches found."

    total = len(matches)
    shown = matches[:20]
    result_str = "\n\n".join(shown)
    if total > 20:
        result_str += f"\n\n... and {total - 20} more files (refine your pattern)"
    return result_str


def run_find_files(pattern: str, path: str, max_results: int = 100) -> str:
    """Find files by glob pattern using ripgrep --files."""
    cmd = ["rg", "--files", "--glob", pattern, path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        return "Error: ripgrep (rg) not found."
    except subprocess.TimeoutExpired:
        return "Error: search timed out."

    files = [l for l in result.stdout.splitlines() if l.strip()]
    if not files:
        return "No files found."

    shown = files[:max_results]
    out = "\n".join(shown)
    if len(files) > max_results:
        out += f"\n... and {len(files) - max_results} more"
    return out


def read_file_lines(path: str, start: int = 1, end: int | None = None, max_lines: int = 200) -> str:
    """Read a file, optionally sliced by line range."""
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    if not p.is_file():
        return f"Error: not a file: {path}"

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"Error reading file: {e}"

    total = len(lines)
    s = max(1, start) - 1
    e = min(end, total) if end else min(s + max_lines, total)

    if e - s > max_lines:
        e = s + max_lines

    numbered = [f"{i + 1:5}: {l}" for i, l in enumerate(lines[s:e], start=s)]
    result = "\n".join(numbered)
    if e < total:
        result += f"\n... ({total - e} more lines, use start/end to read further)"
    return result


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_code",
            description=(
                "Search for a pattern in source code using ripgrep. "
                "Returns matching lines with surrounding context. "
                "Use this to find function definitions, usages, imports, strings, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex or literal pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file path to search in (absolute or relative)",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Optional glob to restrict file types, e.g. '*.py' or '**/*.ts'",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context around each match (default 2)",
                        "default": 2,
                    },
                },
                "required": ["pattern", "path"],
            },
        ),
        types.Tool(
            name="find_files",
            description=(
                "Find files by name/glob pattern inside a directory. "
                "Use this to locate files before reading them."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '*.py', '**/*controller*', 'src/**/*.ts'",
                    },
                    "path": {
                        "type": "string",
                        "description": "Root directory to search in",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default 100)",
                        "default": 100,
                    },
                },
                "required": ["pattern", "path"],
            },
        ),
        types.Tool(
            name="read_file",
            description=(
                "Read a source file, optionally a specific line range. "
                "Max 200 lines per call — use start/end for large files."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "start": {
                        "type": "integer",
                        "description": "First line to read (1-based, default 1)",
                        "default": 1,
                    },
                    "end": {
                        "type": "integer",
                        "description": "Last line to read (inclusive, default start+200)",
                    },
                },
                "required": ["path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "search_code":
        result = run_ripgrep(
            pattern=arguments["pattern"],
            path=arguments["path"],
            file_glob=arguments.get("file_glob"),
            context_lines=arguments.get("context_lines", 2),
        )
    elif name == "find_files":
        result = run_find_files(
            pattern=arguments["pattern"],
            path=arguments["path"],
            max_results=arguments.get("max_results", 100),
        )
    elif name == "read_file":
        result = read_file_lines(
            path=arguments["path"],
            start=arguments.get("start", 1),
            end=arguments.get("end"),
        )
    else:
        result = f"Unknown tool: {name}"

    return [types.TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
