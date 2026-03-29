import asyncio
import hashlib
import json
import logging
import os
import pickle
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import tomllib
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Логирование ───────────────────────────────────────────────────────────────

log_file = Path.home() / ".space-ngrams" / "server.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(log_file),
    ],
)
logger = logging.getLogger("space-ngrams")

server = Server("space-ngrams")


# ── Конфигурация ──────────────────────────────────────────────────────────────

@dataclass
class Config:
    """Конфигурация сервера."""
    # Кэширование
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300  # 5 минут
    max_cache_size_mb: int = 50

    # Лимиты поиска
    max_search_results: int = 50
    max_files_results: int = 100
    max_read_lines: int = 200
    default_context_lines: int = 2
    search_timeout_seconds: int = 15

    # Игноры (дополнительно к .gitignore)
    ignore_patterns: list[str] = field(default_factory=list)

    # Метрики
    metrics_enabled: bool = True

    @classmethod
    def load(cls) -> "Config":
        """Загружает конфигурацию из файла или возвращает значения по умолчанию."""
        config_paths = [
            Path.cwd() / "space-ngrams.toml",
            Path.home() / ".space-ngrams" / "config.toml",
        ]

        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, "rb") as f:
                        data = tomllib.load(f)
                    return cls(
                        cache_enabled=data.get("cache", {}).get("enabled", True),
                        cache_ttl_seconds=data.get("cache", {}).get("ttl_seconds", 300),
                        max_cache_size_mb=data.get("cache", {}).get("max_size_mb", 50),
                        max_search_results=data.get("limits", {}).get("max_search_results", 50),
                        max_files_results=data.get("limits", {}).get("max_files_results", 100),
                        max_read_lines=data.get("limits", {}).get("max_read_lines", 200),
                        default_context_lines=data.get("limits", {}).get("default_context_lines", 2),
                        search_timeout_seconds=data.get("limits", {}).get("search_timeout_seconds", 15),
                        ignore_patterns=data.get("ignore_patterns", []),
                        metrics_enabled=data.get("metrics", {}).get("enabled", True),
                    )
                except Exception as e:
                    logger.warning(f"Ошибка чтения конфига {config_path}: {e}")

        return cls()


# ── Кэширование ───────────────────────────────────────────────────────────────

@dataclass
class CacheEntry:
    """Запись в кэше."""
    result: str
    timestamp: float
    size_bytes: int


class SearchCache:
    """Кэш для результатов поиска с TTL и лимитом размера."""

    def __init__(self, ttl_seconds: int, max_size_mb: int):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.cache: dict[str, CacheEntry] = {}
        self.cache_dir = Path.home() / ".space-ngrams" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _make_key(self, **kwargs) -> str:
        """Создаёт хэш-ключ из параметров."""
        key_str = json.dumps(kwargs, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, **kwargs) -> str | None:
        """Получает значение из кэша."""
        key = self._make_key(**kwargs)
        entry = self.cache.get(key)

        if entry is None:
            return None

        if datetime.now() - datetime.fromtimestamp(entry.timestamp) > self.ttl:
            del self.cache[key]
            return None

        logger.info(f"Cache HIT: {key[:8]}...")
        return entry.result

    def set(self, result: str, **kwargs) -> None:
        """Сохраняет значение в кэш."""
        key = self._make_key(**kwargs)
        entry = CacheEntry(
            result=result,
            timestamp=time.time(),
            size_bytes=len(result.encode()),
        )
        self.cache[key] = entry
        logger.info(f"Cache SET: {key[:8]}... ({entry.size_bytes} bytes)")
        self._cleanup_if_needed()
        self._save_to_disk()

    def _cleanup_if_needed(self) -> None:
        """Удаляет старые записи при превышении лимита."""
        total_size = sum(e.size_bytes for e in self.cache.values())

        if total_size > self.max_size_bytes:
            # Сортируем по времени и удаляем старые
            sorted_keys = sorted(
                self.cache.keys(),
                key=lambda k: self.cache[k].timestamp,
            )
            for key in sorted_keys:
                del self.cache[key]
                if sum(e.size_bytes for e in self.cache.values()) <= self.max_size_bytes:
                    break

    def _save_to_disk(self) -> None:
        """Сохраняет кэш на диск для персистентности между сессиями."""
        try:
            with open(self.cache_dir / "cache.pkl", "wb") as f:
                pickle.dump(
                    {k: (v.result, v.timestamp, v.size_bytes) for k, v in self.cache.items()},
                    f,
                )
        except Exception as e:
            logger.warning(f"Ошибка сохранения кэша: {e}")

    def _load_from_disk(self) -> None:
        """Загружает кэш с диска."""
        try:
            cache_file = self.cache_dir / "cache.pkl"
            if cache_file.exists():
                with open(cache_file, "rb") as f:
                    data = pickle.load(f)
                for k, (result, ts, size) in data.items():
                    self.cache[k] = CacheEntry(result=result, timestamp=ts, size_bytes=size)
                logger.info(f"Загружено {len(self.cache)} записей кэша с диска")
        except Exception as e:
            logger.warning(f"Ошибка загрузки кэша: {e}")


# ── Метрики ───────────────────────────────────────────────────────────────────

@dataclass
class MetricEntry:
    """Запись метрики."""
    timestamp: datetime
    tool_name: str
    duration_ms: float
    cache_hit: bool
    result_size: int


class MetricsCollector:
    """Сборщик метрик для анализа производительности."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.entries: list[MetricEntry] = []
        self.max_entries = 1000

    def record(
        self,
        tool_name: str,
        duration_ms: float,
        cache_hit: bool,
        result_size: int,
    ) -> None:
        """Записывает метрику."""
        if not self.enabled:
            return

        entry = MetricEntry(
            timestamp=datetime.now(),
            tool_name=tool_name,
            duration_ms=duration_ms,
            cache_hit=cache_hit,
            result_size=result_size,
        )
        self.entries.append(entry)

        # Оставляем только последние записи
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        # Логируем
        cache_status = "HIT" if cache_hit else "MISS"
        logger.info(
            f"METRIC | {tool_name:15} | {duration_ms:8.2f}ms | {cache_status:4} | "
            f"{result_size:6} bytes",
        )

    def get_stats(self) -> dict[str, Any]:
        """Возвращает статистику по метрикам."""
        if not self.entries:
            return {"error": "No metrics collected"}

        by_tool: dict[str, list[MetricEntry]] = {}
        for entry in self.entries:
            by_tool.setdefault(entry.tool_name, []).append(entry)

        stats = {}
        for tool_name, entries in by_tool.items():
            durations = [e.duration_ms for e in entries]
            cache_hits = sum(1 for e in entries if e.cache_hit)

            stats[tool_name] = {
                "total_calls": len(entries),
                "cache_hits": cache_hits,
                "cache_hit_rate": cache_hits / len(entries) * 100 if entries else 0,
                "avg_duration_ms": sum(durations) / len(durations),
                "min_duration_ms": min(durations),
                "max_duration_ms": max(durations),
            }

        return stats


# ── Глобальные объекты ────────────────────────────────────────────────────────

config = Config.load()
cache = SearchCache(
    ttl_seconds=config.cache_ttl_seconds,
    max_size_mb=config.max_cache_size_mb,
)
metrics = MetricsCollector(enabled=config.metrics_enabled)

logger.info(f"Конфигурация загружена: cache={config.cache_enabled}, "
            f"metrics={config.metrics_enabled}, timeout={config.search_timeout_seconds}s")


# ── Основные функции ──────────────────────────────────────────────────────────

def run_ripgrep(
    pattern: str,
    path: str,
    file_glob: str | None = None,
    context_lines: int = 2,
) -> tuple[str, bool]:
    """
    Запускает ripgrep и возвращает результаты.

    Returns:
        (результат, was_cached)
    """
    # Проверяем кэш
    if config.cache_enabled:
        cached = cache.get(
            tool="search_code",
            pattern=pattern,
            path=path,
            file_glob=file_glob,
            context_lines=context_lines,
        )
        if cached:
            return cached, True

    # Формируем команду
    cmd = [
        "rg",
        "--json",
        "--max-count", str(config.max_search_results),
        "--context", str(context_lines),
    ]

    # Добавляем игноры из конфига
    for ignore_pattern in config.ignore_patterns:
        cmd += ["--glob", f"!{ignore_pattern}"]

    if file_glob:
        cmd += ["--glob", file_glob]

    cmd += [pattern, path]

    start_time = time.perf_counter()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.search_timeout_seconds,
        )
    except FileNotFoundError:
        return (
            "Error: ripgrep (rg) not found. Install it: "
            "https://github.com/BurntSushi/ripgrep#installation",
            False,
        )
    except subprocess.TimeoutExpired:
        return f"Error: search timed out after {config.search_timeout_seconds} seconds", False

    if result.returncode not in (0, 1):
        return f"Error: {result.stderr.strip()}", False

    # Парсим результаты
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
        return "No matches found.", False

    total = len(matches)
    shown = matches[:20]
    result_str = "\n\n".join(shown)
    if total > 20:
        result_str += f"\n\n... and {total - 20} more files (refine your pattern)"

    # Сохраняем в кэш
    if config.cache_enabled:
        cache.set(
            result_str,
            tool="search_code",
            pattern=pattern,
            path=path,
            file_glob=file_glob,
            context_lines=context_lines,
        )

    duration_ms = (time.perf_counter() - start_time) * 1000
    return result_str, False, duration_ms


def run_find_files(
    pattern: str,
    path: str,
    max_results: int = 100,
) -> tuple[str, bool, float]:
    """
    Ищет файлы по glob-паттерну.

    Returns:
        (результат, was_cached, duration_ms)
    """
    # Проверяем кэш
    if config.cache_enabled:
        cached = cache.get(
            tool="find_files",
            pattern=pattern,
            path=path,
            max_results=max_results,
        )
        if cached:
            return cached, True, 0

    cmd = ["rg", "--files", "--glob", pattern, path]

    start_time = time.perf_counter()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.search_timeout_seconds,
        )
    except FileNotFoundError:
        return "Error: ripgrep (rg) not found.", False, 0
    except subprocess.TimeoutExpired:
        return "Error: search timed out.", False, 0

    files = [l for l in result.stdout.splitlines() if l.strip()]

    if not files:
        return "No files found.", False, (time.perf_counter() - start_time) * 1000

    shown = files[:max_results]
    out = "\n".join(shown)
    if len(files) > max_results:
        out += f"\n... and {len(files) - max_results} more"

    # Сохраняем в кэш
    if config.cache_enabled:
        cache.set(
            out,
            tool="find_files",
            pattern=pattern,
            path=path,
            max_results=max_results,
        )

    duration_ms = (time.perf_counter() - start_time) * 1000
    return out, False, duration_ms


def read_file_lines(
    path: str,
    start: int = 1,
    end: int | None = None,
) -> tuple[str, bool, float]:
    """
    Читает файл построчно.

    Returns:
        (результат, was_cached, duration_ms)
    """
    start_time = time.perf_counter()

    # Проверяем кэш
    if config.cache_enabled:
        cached = cache.get(
            tool="read_file",
            path=path,
            start=start,
            end=end,
        )
        if cached:
            return cached, True, 0

    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}", False, 0
    if not p.is_file():
        return f"Error: not a file: {path}", False, 0

    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"Error reading file: {e}", False, 0

    total = len(lines)
    s = max(1, start) - 1
    e = min(end, total) if end else min(s + config.max_read_lines, total)

    if e - s > config.max_read_lines:
        e = s + config.max_read_lines

    numbered = [f"{i + 1:5}: {l}" for i, l in enumerate(lines[s:e], start=s)]
    result = "\n".join(numbered)
    if e < total:
        result += f"\n... ({total - e} more lines, use start/end to read further)"

    # Сохраняем в кэш
    if config.cache_enabled:
        cache.set(
            result,
            tool="read_file",
            path=path,
            start=start,
            end=end,
        )

    duration_ms = (time.perf_counter() - start_time) * 1000
    return result, False, duration_ms


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_code",
            description=(
                "Search for a pattern in source code using ripgrep. "
                "Returns matching lines with surrounding context. "
                "Use this to find function definitions, usages, imports, strings, etc. "
                f"Results are cached for {config.cache_ttl_seconds}s."
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
                        "description": f"Lines of context around each match (default {config.default_context_lines})",
                        "default": config.default_context_lines,
                    },
                },
                "required": ["pattern", "path"],
            },
        ),
        types.Tool(
            name="find_files",
            description=(
                "Find files by name/glob pattern inside a directory. "
                "Use this to locate files before reading them. "
                f"Results are cached for {config.cache_ttl_seconds}s."
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
                        "description": f"Maximum number of results (default {config.max_files_results})",
                        "default": config.max_files_results,
                    },
                },
                "required": ["pattern", "path"],
            },
        ),
        types.Tool(
            name="read_file",
            description=(
                "Read a source file, optionally a specific line range. "
                f"Max {config.max_read_lines} lines per call — use start/end for large files. "
                "Results are cached."
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
        types.Tool(
            name="get_metrics",
            description=(
                "Get performance metrics for the current session. "
                "Returns statistics on tool usage, cache hit rates, and latencies."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    start_time = time.perf_counter()
    cache_hit = False

    if name == "search_code":
        result, cache_hit, duration_ms = run_ripgrep(
            pattern=arguments["pattern"],
            path=arguments["path"],
            file_glob=arguments.get("file_glob"),
            context_lines=arguments.get("context_lines", config.default_context_lines),
        )
    elif name == "find_files":
        result, cache_hit, duration_ms = run_find_files(
            pattern=arguments["pattern"],
            path=arguments["path"],
            max_results=arguments.get("max_results", config.max_files_results),
        )
    elif name == "read_file":
        result, cache_hit, duration_ms = read_file_lines(
            path=arguments["path"],
            start=arguments.get("start", 1),
            end=arguments.get("end"),
        )
    elif name == "get_metrics":
        stats = metrics.get_stats()
        result = json.dumps(stats, indent=2, default=str)
        duration_ms = (time.perf_counter() - start_time) * 1000
    else:
        result = f"Unknown tool: {name}"
        duration_ms = 0

    # Записываем метрику (кроме get_metrics)
    if name != "get_metrics":
        metrics.record(
            tool_name=name,
            duration_ms=duration_ms,
            cache_hit=cache_hit,
            result_size=len(result.encode()),
        )

    return [types.TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
