# pg-mcp

Natural language PostgreSQL query service via MCP (Model Context Protocol). Uses OpenAI to translate natural language into SQL, validates and executes it safely, and returns results to any MCP-compatible client.

## Features

- Natural language to SQL via OpenAI
- Auto-discovers database schema on startup (tables, views, columns, indexes, foreign keys, enums)
- Schema cache with optional disk persistence
- SQL safety validation (SELECT-only, dangerous function blocking, LIMIT enforcement)
- Read-only transaction execution with configurable timeout
- Result validation with automatic retry on empty results
- Supports multiple databases

## Requirements

- Python 3.11+
- PostgreSQL
- OpenAI API key

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PG_MCP_DATABASES` | Yes | — | Comma-separated PostgreSQL connection strings |
| `PG_MCP_DEFAULT_DB` | No | First DSN | Default database for queries |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o` | Model to use for SQL generation |
| `OPENAI_BASE_URL` | No | OpenAI default | Custom endpoint (Azure, proxy, etc.) |
| `PG_MCP_QUERY_TIMEOUT` | No | `30` | Query timeout in seconds |
| `PG_MCP_MAX_ROWS` | No | `100` | Max rows returned (1-1000) |
| `PG_MCP_SCHEMA_CACHE_PATH` | No | None | Path for persistent schema cache |
| `PG_MCP_LOG_LEVEL` | No | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Multiple databases example:

```
PG_MCP_DATABASES=postgresql://user:pass@host1:5432/db1,postgresql://user:pass@host2:5432/db2
```

## Usage with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pg-mcp": {
      "command": "python3",
      "args": ["-m", "pg_mcp.server"],
      "env": {
        "PG_MCP_DATABASES": "postgresql://user:pass@localhost:5432/mydb",
        "OPENAI_API_KEY": "sk-...",
        "PG_MCP_SCHEMA_CACHE_PATH": "~/.cache/pg-mcp/schema.json"
      }
    }
  }
}
```

## MCP Tools

### `query`

Query a database using natural language.

```json
{
  "question": "What are the top 10 customers by sales last month?",
  "database": "mydb",
  "return_sql": false,
  "max_rows": 100
}
```

- `return_sql: true` — returns the generated SQL without executing
- `return_sql: false` (default) — executes and returns results

### `list_databases`

List all accessible databases with summary info.

### `describe_database`

Get detailed schema info for a database.

```json
{
  "database": "mydb",
  "schema": "public",
  "pattern": "user"
}
```

### `refresh_schema`

Reload schema cache from the database.

```json
{
  "database": "mydb"
}
```

Omit `database` to refresh all databases.

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## How It Works

```
User question
  → Schema context assembled from cache
  → OpenAI generates SQL
  → Safety validation (SELECT-only, no dangerous functions, LIMIT injection)
  → Execute in read-only transaction with timeout
  → Optional result validation on empty results
  → Return SQL or query results
```

## Security

- Generated SQL is validated to be SELECT-only (including CTE checks)
- Dangerous PostgreSQL functions are blocked (`pg_sleep`, `lo_import`, etc.)
- All queries execute in read-only transactions
- Automatic LIMIT enforcement prevents large result sets
- Query timeout prevents long-running queries
- Connection passwords never appear in logs or API responses
