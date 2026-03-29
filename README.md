# space-ngrams

MCP server for fast code search. Connects to Claude Code, Codex CLI, Qwen CLI, and OpenCode as a set of ripgrep-based search tools.

## Tools

| Tool | Description |
|---|---|
| `search_code` | Search for a pattern or regex in code with surrounding context |
| `find_files` | Find files by glob pattern |
| `read_file` | Read a file with optional line range (max 200 lines per call) |

## Requirements

- Python 3.11+
- [ripgrep](https://github.com/BurntSushi/ripgrep) in PATH
- Python package `mcp >= 1.0.0`

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/space-ngrams.git
cd space-ngrams
```

### 2. Install ripgrep

```bash
# Windows
winget install BurntSushi.ripgrep.MSVC

# macOS
brew install ripgrep

# Linux
sudo apt install ripgrep
```

Verify: `rg --version`

### 3. Install Python dependencies

```bash
pip install mcp
```

### 4. Verify the server starts

```bash
python src/server.py
```

The process should hang (waiting on stdin) — that's correct. Stop with `Ctrl+C`.

## Connecting to AI tools

### Claude Code

```bash
claude mcp add space-ngrams -- python /path/to/space-ngrams/src/server.py
```

Verify:
```bash
claude mcp list
# space-ngrams: python ... - ✓ Connected
```

### Codex CLI

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.space-ngrams]
command = "python"
args = [ "/path/to/space-ngrams/src/server.py" ]
```

### Qwen CLI

Add to `~/.qwen/settings.json`:

```json
{
  "mcpServers": {
    "space-ngrams": {
      "command": "python",
      "args": ["/path/to/space-ngrams/src/server.py"]
    }
  }
}
```

### OpenCode

Add to `opencode.json` in your project root or home directory:

```json
{
  "mcp": {
    "space-ngrams": {
      "type": "local",
      "command": ["python", "/path/to/space-ngrams/src/server.py"]
    }
  }
}
```

## Usage

The tools are available automatically — the agent decides when to use them. You can also ask explicitly:

```
find all calls to getUserById in D:/Projects/MyApp
```

```
show all .ts files in the src folder
```

```
read D:/Projects/MyApp/src/auth/service.ts lines 50-100
```

### search_code parameters

| Parameter | Required | Description |
|---|---|---|
| `pattern` | yes | Regex or literal string |
| `path` | yes | Directory or file to search in |
| `file_glob` | no | File type filter, e.g. `*.py` or `**/*.ts` |
| `context_lines` | no | Lines of context around each match (default: 2) |

### find_files parameters

| Parameter | Required | Description |
|---|---|---|
| `pattern` | yes | Glob, e.g. `*.py`, `**/*controller*` |
| `path` | yes | Root directory to search in |
| `max_results` | no | Maximum results (default: 100) |

### read_file parameters

| Parameter | Required | Description |
|---|---|---|
| `path` | yes | Absolute or relative path to the file |
| `start` | no | First line to read (default: 1) |
| `end` | no | Last line inclusive |

## Project structure

```
space-ngrams/
├── src/
│   └── server.py      # MCP server
├── pyproject.toml     # Package metadata
├── LICENSE
└── README.md
```

## License

MIT
