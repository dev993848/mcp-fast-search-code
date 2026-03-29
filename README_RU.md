# space-ngrams

**MCP-сервер, который даёт AI-агентам суперспособность искать по вашей кодовой базе со скоростью молнии.**

Space-nGrams подключается к AI-ассистентам (Claude Code, Codex CLI, Qwen CLI, OpenCode) и предоставляет им три основных инструмента: поиск по коду, поиск файлов и чтение файлов. Всё работает на [ripgrep](https://github.com/BurntSushi/ripgrep) с производительностью в миллисекунды.

---

## 🏗️ Как это работает

### Архитектура

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

### Зачем нужен MCP?

**MCP (Model Context Protocol)** — это стандарт, позволяющий AI-агентам получать доступ к внешним инструментам и данным. Вместо того чтобы загружать весь ваш код в контекст AI (что медленно и дорого), Space-nGrams даёт AI возможность:

1. **Искать по требованию** — Найти любой паттерн, функцию или строку в коде за миллисекунды
2. **Навигировать эффективно** — Найти файлы по имени, затем прочитать только нужное
3. **Работать с большими кодовыми базами** — Не нужно загружать всё в контекст

### Зачем ripgrep?

- **Очень быстрый** — SIMD ускорение, компиляция regex, параллельный поиск
- **Умная фильтрация** — Уважает `.gitignore`, пропускает бинарные файлы
- **Богатый вывод** — JSON формат с номерами строк и контекстом
- **Проверен в бою** — Используется разработчиками ежедневно

### Зачем кэширование?

Повторные поиски обычны, когда AI исследует код. Наш слой кэширования:
- Хранит результаты 5 минут (настраивается)
- Сохраняется между сессиями на диске
- Уменьшает задержку с ~100мс до ~2мс при попадании в кэш
- Автоматически управляет лимитами размера (50 MB по умолчанию)

---

## ⚡ Возможности

| Возможность | Преимущество |
|---|---|
| **Кэширование** | В 10-50 раз быстрее при повторных запросах |
| **Метрики** | Отслеживание производительности и cache hit rate |
| **Конфигурация** | Настройка лимитов, таймаутов, паттернов игнорирования |
| **Логирование** | Отладка через `~/.space-ngrams/server.log` |

---

## 🛠️ Инструменты

| Инструмент | Описание |
|---|---|
| `search_code` | Поиск по паттерну/regex в коде с контекстом |
| `find_files` | Поиск файлов по glob-паттерну |
| `read_file` | Чтение файла (макс. 200 строк/вызов) |
| `get_metrics` | Статистика производительности сессии |

---

## 📦 Установка

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/your-username/space-ngrams.git
cd space-ngrams
```

### 2. Установите ripgrep

```bash
# Windows
winget install BurntSushi.ripgrep.MSVC

# macOS
brew install ripgrep

# Linux
sudo apt install ripgrep
```

Проверка: `rg --version`

### 3. Установите Python-зависимости

```bash
pip install mcp
```

### 4. Проверите запуск сервера

```bash
python src/server.py
```

Процесс будет ждать stdin — это правильно. Остановка: `Ctrl+C`.

---

## 🔌 Подключение к AI-инструментам

### Claude Code

```bash
claude mcp add space-ngrams -- python /path/to/space-ngrams/src/server.py
```

Проверка:
```bash
claude mcp list
# space-ngrams: python ... - ✓ Connected
```

### Codex CLI

Добавьте в `~/.codex/config.toml`:

```toml
[mcp_servers.space-ngrams]
command = "python"
args = [ "/path/to/space-ngrams/src/server.py" ]
```

### Qwen CLI

Добавьте в `~/.qwen/settings.json`:

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

Добавьте в `opencode.json` в корне проекта или домашней директории:

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

## 💬 Использование

AI-агент автоматически использует эти инструменты при необходимости. Вы также можете вызывать их явно:

```
найди все вызовы getUserById в D:/Projects/MyApp
```

```
покажи все .ts файлы в папке src
```

```
прочитай D:/Projects/MyApp/src/auth/service.ts строки 50-100
```

### Параметры инструментов

#### search_code
| Параметр | Обязательный | Описание |
|---|---|---|
| `pattern` | да | Regex или строка для поиска |
| `path` | да | Директория или файл для поиска |
| `file_glob` | нет | Фильтр файлов, например `*.py` или `**/*.ts` |
| `context_lines` | нет | Строк контекста (по умолчанию: 2) |

#### find_files
| Параметр | Обязательный | Описание |
|---|---|---|
| `pattern` | да | Glob, например `*.py`, `**/*controller*` |
| `path` | да | Корневая директория для поиска |
| `max_results` | нет | Максимум результатов (по умолчанию: 100) |

#### read_file
| Параметр | Обязательный | Описание |
|---|---|---|
| `path` | да | Абсолютный или относительный путь |
| `start` | нет | Первая строка для чтения (по умолчанию: 1) |
| `end` | нет | Последняя строка (включительно) |

#### get_metrics

Возвращает статистику производительности:

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

## ⚙️ Конфигурация

Создайте файл конфигурации: `./space-ngrams.toml` (для проекта) или `~/.space-ngrams/config.toml` (глобально):

```toml
[cache]
enabled = true
ttl_seconds = 300       # 5 минут
max_size_mb = 50

[limits]
max_search_results = 50
max_files_results = 100
max_read_lines = 200
default_context_lines = 2
search_timeout_seconds = 15

[ignore_patterns]
# Дополнительные паттерны для игнорирования (кроме .gitignore)
ignore_patterns = [
    "*.log",
    "*.tmp",
    "node_modules/**",
    "__pycache__/**",
]

[metrics]
enabled = true
```

Полный пример с комментариями см. в `space-ngrams.example.toml`.

---

## 📁 Структура проекта

```
space-ngrams/
├── src/
│   └── server.py           # MCP сервер
├── pyproject.toml          # Метаданные Python-пакета
├── space-ngrams.example.toml  # Пример конфигурации
├── LICENSE
├── README.md               # Английская версия
├── README_RU.md            # Этот файл (русский)
└── docs/
    └── ARCHITECTURE.md     # Заметки об архитектуре (опционально)
```

📖 Также доступно на [English](README.md).

---

## 📊 Логи и кэш

| Расположение | Назначение |
|---|---|
| `~/.space-ngrams/server.log` | Логи сервера и метрики |
| `~/.space-ngrams/cache/` | Постоянное хранилище кэша |

---

## 📄 Лицензия

MIT
