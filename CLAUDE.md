# CLAUDE.md — postgres-mcp

## Project Overview

PostgreSQL MCP Server: a read-only, natural-language-to-SQL service built on the Model Context Protocol. Users describe queries in natural language; the server uses OpenAI to generate SQL, validates it for safety, executes it in a read-only transaction, and returns results or the SQL itself.

**Status:** Pre-implementation. PRD at `specs/0001-pg-mcp-prd.md`.

## Tech Stack

- **Runtime:** Python 3.11+
- **MCP SDK:** `mcp` (FastMCP, stdio transport only)
- **Database driver:** `asyncpg` (async)
- **SQL parsing / safety:** `sqlglot`
- **Data validation:** `pydantic` v2
- **LLM:** `openai` Python SDK
- **Config:** environment variables / `.env` (via `pydantic-settings`)

## Architecture (single-process, async)

```
MCP Client (stdin/stdout)
  → FastMCP Server
    → SchemaCache (in-memory, startup-loaded)
    → SQLPipeline
      → PromptBuilder (question + schema → prompt)
      → OpenAI client (prompt → raw SQL)
      → SQLValidator (sqlglot: SELECT-only, no dangerous functions, enforce LIMIT)
      → QueryExecutor (asyncpg: read-only txn, timeout, max rows)
      → ResultChecker (optional: OpenAI verifies empty/suspicious results)
```

## Design Principles

### SOLID

- **SRP** — Each module has one reason to change. `schema` owns metadata discovery & caching; `pipeline` owns the NL→SQL→results flow; `validator` owns safety checks; `executor` owns running SQL. Do not mix concerns.
- **OCP** — Use Protocols (abstract base classes / `typing.Protocol`) for external dependencies (OpenAI client, database connection) so they can be swapped without modifying business logic.
- **LSP** — Subtypes must be substitutable. When using inheritance or Protocols, don't violate the contract.
- **ISP** — Keep interfaces small. A class that only needs to execute SQL should not depend on schema-discovery methods.
- **DIP** — High-level policy (pipeline orchestration) depends on abstractions, not on concrete asyncpg/openai details.

### DRY

- Repeated schema-query SQL fragments go into one place (a `queries` module or SQL template constants).
- Prompt templates live in a single dedicated module; don't inline prompt strings in business logic.
- Shared validation / transformation helpers are centralized.

### YAGNI

- No multi-turn conversation state (per PRD Q1).
- No query history persistence (per PRD Q3).
- No SSE transport (per PRD Q4).
- Do not build abstraction layers "just in case." Extract a Protocol or helper only when a second consumer appears.

## Python Style Guidelines

### General

- Follow **PEP 8** and the spirit of **PEP 20** (Zen of Python).
- Use `async`/`await` throughout — this is an async application.
- Prefer `asyncpg` connection pools; acquire connections via `async with pool.acquire()`.
- Use `pydantic` models for all configuration and MCP tool input/output schemas. Never parse raw dicts by hand.
- Use `structlog` or stdlib `logging` with structured fields — never bare `print()` for operational output.

### Idiomatic Patterns

```python
# Good: use enums for bounded sets of choices
from enum import StrEnum

class QueryStatus(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    VALIDATION_FAILED = "validation_failed"

# Good: use dataclasses / pydantic models, not raw tuples or dicts
from pydantic import BaseModel

class QueryResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int

# Good: context managers for resources
async with pool.acquire() as conn:
    async with conn.transaction(readonly=True):
        ...

# Good: guard clauses / early returns, avoid deep nesting
def validate(sql: str) -> None:
    if not sql.strip():
        raise ValueError("Empty SQL")
    if not is_select(sql):
        raise ValueError("Only SELECT statements allowed")

# Good: use typing.Protocol for dependency inversion
from typing import Protocol

class SQLExecutor(Protocol):
    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]: ...
```

### Naming Conventions

- Modules: `snake_case` — e.g., `schema_cache.py`, `sql_validator.py`.
- Classes: `PascalCase` — e.g., `SchemaCache`, `SQLPipeline`.
- Functions / methods: `snake_case` — e.g., `refresh_schema()`, `build_prompt()`.
- Constants: `UPPER_SNAKE_CASE` — e.g., `MAX_ROWS`, `DEFAULT_TIMEOUT`.
- Private helpers: leading underscore `_build_select_clause`.
- Boolean variables / functions: `is_*`, `has_*`, `should_*` — e.g., `is_read_only()`.

### Error Handling

- Use custom exception hierarchy rooted in a project `PostgresMCPError`:
  ```
  PostgresMCPError
  ├── DatabaseUnavailableError
  ├── SQLValidationError
  ├── QueryExecutionError
  ├── QueryTimeoutError
  └── LLMError
  ```
- Raise specific exceptions; catch and map to MCP error responses at the tool boundary only. Do not blanket-catch `Exception` in business logic.
- Use `try/except` around external I/O (database, OpenAI); let programming bugs crash loudly.
- Never expose internal stack traces or connection strings in error responses.

### Imports

- Use `from __future__ import annotations` at the top of every module for forward-reference support.
- Order: stdlib → third-party → local, separated by blank lines.
- Avoid wildcard imports (`from module import *`).

### Type Annotations

- All public functions and methods must have full type annotations.
- Use `from typing import ...` or built-in generics (`list[str]`, `dict[str, Any]`).
- Use `TypedDict` or Pydantic models for structured data flowing across module boundaries.

### Testing

- Test framework: `pytest` + `pytest-asyncio`.
- One test file per source module: `test_sql_validator.py` mirrors `sql_validator.py`.
- Use `fixtures` and `@pytest.mark.asyncio` for async tests.
- Mock external services (OpenAI, asyncpg) with `unittest.mock.AsyncMock` or `pytest-mock`.
- Aim for tests at the unit level; integration tests can spin up a real Postgres via Docker.

### Project Structure (target)

```
postgres-mcp/
├── src/
│   └── pg_mcp/
│       ├── __init__.py
│       ├── __main__.py          # entry point: `python -m pg_mcp`
│       ├── server.py            # FastMCP app, tool registration
│       ├── config.py            # pydantic-settings configuration
│       ├── schema_cache.py      # DB metadata discovery & caching
│       ├── pipeline.py          # NL → SQL → results orchestration
│       ├── prompt_builder.py    # Assembles LLM prompts
│       ├── sql_validator.py     # Safety checks via sqlglot
│       ├── executor.py          # asyncpg read-only execution
│       ├── result_checker.py    # Optional LLM-based result verification
│       ├── errors.py            # Custom exception hierarchy
│       └── queries/             # SQL fragments for metadata queries
│           └── schema.sql
├── tests/
├── specs/
├── pyproject.toml
├── .env.example
└── CLAUDE.md
```

## Key Rules

1. **Read-only enforcement** — Every SQL statement must pass `sqlglot` validation as SELECT/WITH…SELECT before execution. No exceptions.
2. **Connection strings are secrets** — Never log, return, or cache raw connection strings. Mask passwords in all output.
3. **LIMIT always applied** — If generated SQL lacks LIMIT, append one. Default 100, hard cap 1000.
4. **Timeout on every query** — Default 30 s, configurable. Use `asyncio.wait_for` or asyncpg statement timeout.
5. **Fail open for individual databases** — If one DB is unreachable at startup, log a warning and continue serving others.
6. **No premature abstraction** — Don't build plugin systems, strategy patterns, or configuration-driven dispatchers until there are at least two concrete use cases.

## Common Commands

```bash
# Install (after pyproject.toml exists)
pip install -e ".[dev]"

# Run the MCP server
python -m pg_mcp

# Run tests
pytest

# Lint / format
ruff check .
ruff format .
```
