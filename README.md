# space-ngrams

**MCP server that gives AI agents superpowers to search through your codebase at lightning speed.**

Space-nGrams connects to AI coding assistants (Claude Code, Codex CLI, Qwen CLI, OpenCode) and provides them with three essential tools: search code, find files, and read files. All powered by [ripgrep](https://github.com/BurntSushi/ripgrep) for millisecond-level performance.

---

## 🏗️ How It Works

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  AI Agent       │     │  Space-nGrams    │     │  ripgrep        │
│  (Claude Code,  │────▶│  MCP Server      │────▶│  (rg)           │
│   Qwen, etc.)   │◀────│  (Python)        │◀────│  Search Engine  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                       │                         │
        │                       ▼                         │
        │              ┌──────────────────┐               │
        │              │  Cache Layer     │               │
        │              │  (~/.space-ngrams│               │
        │              │   /cache/)       │               │
        │              └──────────────────┘               │
        │                       │                         │
        │                       ▼                         │
        │              ┌──────────────────┐               │
        └─────────────▶│  Metrics & Logs  │◀──────────────┘
                       │  (~/.space-ngrams│
                       │   /server.log)   │
                       └──────────────────┘
```

### Why MCP?

**MCP (Model Context Protocol)** is a standard that allows AI agents to access external tools and data sources. Instead of embedding all your code into the AI's context (which is slow and expensive), Space-nGrams gives the AI the ability to:

1. **Search on demand** — Find any pattern, function, or string in your codebase in milliseconds
2. **Navigate efficiently** — Locate files by name, then read only what's needed
3. **Work with large codebases** — No need to load everything into context

### Why ripgrep?

- **Blazing fast** — SIMD acceleration, regex compilation, parallel search
- **Smart filtering** — Respects `.gitignore`, skips binary files
- **Rich output** — JSON format with line numbers and context
- **Battle tested** — Used by developers worldwide daily

### Why caching?

Repeated searches are common when AI agents explore code. Our cache layer:
- Stores results for 5 minutes (configurable)
- Persists across sessions on disk
- Reduces latency from ~100ms to ~2ms on cache hits
- Automatically manages size limits (50 MB default)

---

## ⚡ Features

| Feature | Benefit |
|---|---|
| **Caching** | 10-50x faster for repeated searches |
| **Metrics** | Track performance and cache hit rates |
| **Configuration** | Customize limits, timeouts, ignore patterns |
| **Logging** | Debug issues via `~/.space-ngrams/server.log` |

---

## 🛠️ Tools

| Tool | Description |
|---|---|
| `search_code` | Search for regex/string in code with context |
| `find_files` | Find files by glob pattern |
| `read_file` | Read file content (max 200 lines/call) |
| `get_metrics` | Get session performance statistics |

---

## 📦 Installation

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

The process will wait on stdin — that's correct. Stop with `Ctrl+C`.

---

## 🔌 Connecting to AI Tools

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

---

## 💬 Usage

The AI agent automatically uses these tools when needed. You can also trigger them explicitly:

```
find all calls to getUserById in D:/Projects/MyApp
```

```
show all .ts files in the src folder
```

```
read D:/Projects/MyApp/src/auth/service.ts lines 50-100
```

### Tool Parameters

#### search_code
| Parameter | Required | Description |
|---|---|---|
| `pattern` | yes | Regex or literal string |
| `path` | yes | Directory or file to search in |
| `file_glob` | no | File type filter, e.g. `*.py` or `**/*.ts` |
| `context_lines` | no | Lines of context (default: 2) |

#### find_files
| Parameter | Required | Description |
|---|---|---|
| `pattern` | yes | Glob, e.g. `*.py`, `**/*controller*` |
| `path` | yes | Root directory to search in |
| `max_results` | no | Maximum results (default: 100) |

#### read_file
| Parameter | Required | Description |
|---|---|---|
| `path` | yes | Absolute or relative path |
| `start` | no | First line to read (default: 1) |
| `end` | no | Last line (inclusive) |

#### get_metrics

Returns performance statistics:

```json
{
  "search_code": {
    "total_calls": 15,
    "cache_hits": 8,
    "cache_hit_rate": 53.3,
    "avg_duration_ms": 45.2,
    "min_duration_ms": 2.1,
    "max_duration_ms": 234.5
  }
}
```

---

## ⚙️ Configuration

Create a config file at `./space-ngrams.toml` (project-specific) or `~/.space-ngrams/config.toml` (global):

```toml
[cache]
enabled = true
ttl_seconds = 300       # 5 minutes
max_size_mb = 50

[limits]
max_search_results = 50
max_files_results = 100
max_read_lines = 200
default_context_lines = 2
search_timeout_seconds = 15

[ignore_patterns]
# Additional patterns to ignore (beyond .gitignore)
ignore_patterns = [
    "*.log",
    "*.tmp",
    "node_modules/**",
    "__pycache__/**",
]

[metrics]
enabled = true
```

See `space-ngrams.example.toml` for a full example with comments.

---

## 📁 Project Structure

```
space-ngrams/
├── src/
│   └── server.py           # MCP server implementation
├── pyproject.toml          # Python package metadata
├── space-ngrams.example.toml  # Example configuration
├── LICENSE
├── README.md               # This file (English)
├── README_RU.md            # Russian translation
└── docs/
    └── ARCHITECTURE.md     # Architecture notes (optional)
```

📖 Also available in [Russian](README_RU.md).

---

## 📊 Logs and Cache

| Location | Purpose |
|---|---|
| `~/.space-ngrams/server.log` | Server logs and metrics |
| `~/.space-ngrams/cache/` | Persistent cache storage |

---

## 📄 License

MIT
