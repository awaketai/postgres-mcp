# 技术设计: PostgreSQL MCP Server

> 基于需求文档 `specs/0001-pg-mcp-prd.md`，使用 FastMCP / Asyncpg / SQLGlot / Pydantic / OpenAI 构建。

---

## 1. 技术栈与依赖

| 组件 | 库 | 版本要求 | 用途 |
|------|---|---------|------|
| MCP Server | `fastmcp` | >= 2.14 | MCP 协议层，tool 注册，stdio transport |
| 数据库驱动 | `asyncpg` | >= 0.30 | 异步 PostgreSQL 连接池与查询执行 |
| SQL 解析 | `sqlglot` | >= 26.0 | SQL AST 解析、安全校验、LIMIT 注入 |
| 数据校验 | `pydantic` | >= 2.0 | 配置模型、Tool 入参/出参的结构化定义 |
| LLM 调用 | `openai` | >= 1.0 | Chat Completions API（支持自定义 base_url） |
| 配置加载 | `pydantic-settings` | >= 2.0 | 从环境变量 / `.env` 加载配置 |
| 日志 | `structlog` | >= 24.0 | 结构化日志输出 |

---

## 2. 项目结构

```
postgres-mcp/
├── pyproject.toml                # 项目元数据、依赖、入口
├── .env.example                  # 配置模板
├── src/
│   └── pg_mcp/
│       ├── __init__.py
│       ├── server.py             # FastMCP 实例、tool 注册、启动入口
│       ├── config.py             # Pydantic Settings 配置模型
│       ├── db/
│       │   ├── __init__.py
│       │   ├── pool.py           # asyncpg 连接池管理
│       │   └── inspector.py      # Schema 元信息采集
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── models.py         # Schema 数据模型（Pydantic）
│       │   ├── cache.py          # Schema 缓存管理（内存 + 可选磁盘持久化）
│       │   └── discover.py       # 启动时 schema 发现与加载编排
│       ├── sql/
│       │   ├── __init__.py
│       │   ├── generator.py      # 调用 OpenAI 生成 SQL
│       │   ├── validator.py      # SQL 安全校验（基于 sqlglot）
│       │   └── executor.py       # 只读事务中执行 SQL
│       └── prompts/
│           ├── __init__.py
│           └── templates.py      # Prompt 模板
├── tests/
│   ├── conftest.py
│   ├── test_validator.py
│   ├── test_generator.py
│   ├── test_inspector.py
│   └── test_server.py
└── specs/
    ├── 0001-pg-mcp-prd.md
    └── 0002-pg-mcp-design.md
```

---

## 3. 配置层设计

### 3.1 配置模型 (`config.py`)

```python
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    # 数据库
    pg_mcp_databases: str = Field(
        description="逗号分隔的 PostgreSQL 连接串",
        examples=["postgresql://user:pass@localhost:5432/mydb"],
    )
    pg_mcp_default_db: str | None = Field(
        default=None,
        description="默认数据库名，不填则使用连接串列表中的第一个",
    )

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None

    # 查询行为
    pg_mcp_query_timeout: int = Field(default=30, ge=1, le=300)
    pg_mcp_max_rows: int = Field(default=100, ge=1, le=1000)

    # Schema 管理
    pg_mcp_schema_refresh_interval: int = Field(
        default=0, description="自动刷新间隔（秒），0 表示关闭",
    )
    pg_mcp_schema_cache_path: str | None = Field(
        default=None,
        description="Schema 缓存持久化路径，不填则仅内存缓存",
    )

    # 日志
    pg_mcp_log_level: str = Field(default="INFO")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("pg_mcp_databases")
    @classmethod
    def validate_dsn_list(cls, v: str) -> str:
        dsns = [d.strip() for d in v.split(",") if d.strip()]
        if not dsns:
            raise ValueError("至少需要一个数据库连接串")
        return v
```

### 3.2 配置来源优先级

由 `pydantic-settings` 内置处理：环境变量 > `.env` 文件。

---

## 4. 数据层设计

### 4.1 连接池管理 (`db/pool.py`)

负责管理多个数据库的 asyncpg 连接池。

```python
import asyncpg
from dataclasses import dataclass


@dataclass
class DatabasePool:
    name: str
    dsn: str
    pool: asyncpg.Pool


class PoolManager:
    """管理多个数据库的连接池。"""

    def __init__(self) -> None:
        self._pools: dict[str, DatabasePool] = {}

    async def initialize(self, dsn_list: list[str]) -> None:
        for dsn in dsn_list:
            name = self._extract_db_name(dsn)
            try:
                pool = await asyncpg.create_pool(
                    dsn,
                    min_size=1,
                    max_size=5,
                    statement_cache_size=0,  # 避免缓存动态 SQL
                )
                self._pools[name] = DatabasePool(name=name, dsn=dsn, pool=pool)
            except Exception as e:
                # NFR-R1: 单库失败不阻塞其他库
                logger.warning("database_connection_failed", db=name, error=str(e))

    async def get(self, database: str) -> asyncpg.Pool:
        entry = self._pools.get(database)
        if entry is None:
            raise ValueError(f"database unavailable: {database}")
        return entry.pool

    async def close(self) -> None:
        for entry in self._pools.values():
            await entry.pool.close()

    def available_databases(self) -> list[str]:
        return list(self._pools.keys())

    @staticmethod
    def _extract_db_name(dsn: str) -> str:
        # 从 postgresql://user:pass@host:port/dbname 中提取 dbname
        ...

    @property
    def default_database(self) -> str:
        return next(iter(self._pools))
```

**关键设计决策：**
- `statement_cache_size=0`：生成的 SQL 每次不同，不需要 prepared statement 缓存。
- 连接池大小 `max_size=5`：MCP stdio 模式下单客户端串行请求，5 足够。

### 4.2 Schema 元信息采集 (`db/inspector.py`)

通过查询 `information_schema` 和 `pg_catalog` 采集元信息。

```python
class SchemaInspector:
    """从 PostgreSQL 采集 schema 元信息。"""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def collect(self) -> DatabaseProfile:
        async with self._pool.acquire() as conn:
            schemas = await self._get_schemas(conn)
            tables = await self._get_tables(conn)
            columns = await self._get_columns(conn)
            views = await self._get_views(conn)
            indexes = await self._get_indexes(conn)
            foreign_keys = await self._get_foreign_keys(conn)
            enums = await self._get_enum_types(conn)
            row_counts = await self._get_row_counts(conn)
        return DatabaseProfile(
            schemas=schemas,
            tables=tables,
            columns=columns,
            views=views,
            indexes=indexes,
            foreign_keys=foreign_keys,
            enums=enums,
            row_counts=row_counts,
        )
```

**核心 SQL 查询示例：**

```sql
-- 表与行数估算
SELECT
    schemaname, relname AS table_name,
    reltuples::bigint AS row_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, relname;

-- 列信息
SELECT
    table_schema, table_name, column_name,
    data_type, is_nullable, column_default,
    col_description(
        quote_ident(table_schema)::regclass,
        ordinal_position
    ) AS column_comment
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;

-- 外键关系
SELECT
    tc.constraint_name,
    tc.table_schema AS from_schema,
    kcu.table_name AS from_table,
    kcu.column_name AS from_column,
    ccu.table_schema AS to_schema,
    ccu.table_name AS to_table,
    ccu.column_name AS to_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';

-- ENUM 类型
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    e.enumlabel AS value
FROM pg_type t
JOIN pg_enum e ON t.oid = e.enumtypid
JOIN pg_namespace n ON n.oid = t.typnamespace
ORDER BY n.nspname, t.typname, e.enumsortorder;
```

---

## 5. Schema 模型与缓存设计

### 5.1 Schema 数据模型 (`schema/models.py`)

```python
from pydantic import BaseModel


class ColumnInfo(BaseModel):
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: str | None = None
    column_comment: str | None = None


class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    row_count: int


class ViewInfo(BaseModel):
    schema_name: str
    view_name: str
    definition: str


class ForeignKeyInfo(BaseModel):
    constraint_name: str
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str


class EnumTypeInfo(BaseModel):
    schema_name: str
    type_name: str
    values: list[str]


class IndexInfo(BaseModel):
    schema_name: str
    table_name: str
    index_name: str
    columns: list[str]
    is_unique: bool


class DatabaseProfile(BaseModel):
    """单个数据库的完整 schema 快照。"""
    database_name: str
    schemas: list[str]
    tables: list[TableInfo]
    columns: list[ColumnInfo]
    views: list[ViewInfo]
    indexes: list[IndexInfo]
    foreign_keys: list[ForeignKeyInfo]
    enums: list[EnumTypeInfo]
```

### 5.2 缓存管理 (`schema/cache.py`)

```python
import json
from pathlib import Path


class SchemaCache:
    """管理多个数据库的 schema 缓存，支持可选的磁盘持久化。"""

    def __init__(self, cache_path: str | None = None) -> None:
        self._profiles: dict[str, DatabaseProfile] = {}
        self._cache_path = Path(cache_path) if cache_path else None

    def get(self, database: str) -> DatabaseProfile | None:
        return self._profiles.get(database)

    def put(self, profile: DatabaseProfile) -> None:
        self._profiles[profile.database_name] = profile

    def list_databases(self) -> list[str]:
        return list(self._profiles.keys())

    def all_profiles(self) -> dict[str, DatabaseProfile]:
        return dict(self._profiles)

    # ---- 磁盘持久化（Q5: 可选） ----

    def save_to_disk(self) -> None:
        if not self._cache_path:
            return
        data = {name: p.model_dump() for name, p in self._profiles.items()}
        self._cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def load_from_disk(self) -> set[str]:
        """从磁盘加载缓存，返回成功加载的数据库名集合。"""
        if not self._cache_path or not self._cache_path.exists():
            return set()
        data = json.loads(self._cache_path.read_text())
        loaded = set()
        for name, profile_data in data.items():
            try:
                self._profiles[name] = DatabaseProfile(**profile_data)
                loaded.add(name)
            except Exception:
                logger.warning("cache_load_failed", db=name)
        return loaded
```

### 5.3 Schema 发现编排 (`schema/discover.py`)

```python
class SchemaDiscoverer:
    """启动时编排 schema 发现流程。"""

    def __init__(
        self,
        pool_manager: PoolManager,
        cache: SchemaCache,
    ) -> None:
        self._pool_manager = pool_manager
        self._cache = cache

    async def discover_all(self, skip_existing: bool = False) -> None:
        # 尝试从磁盘加载
        disk_loaded = self._cache.load_from_disk()

        for db_name in self._pool_manager.available_databases():
            if skip_existing and db_name in disk_loaded:
                logger.info("schema_loaded_from_cache", db=db_name)
                continue

            pool = await self._pool_manager.get(db_name)
            inspector = SchemaInspector(pool)
            profile = await inspector.collect()
            profile.database_name = db_name
            self._cache.put(profile)
            logger.info("schema_discovered", db=db_name)

        self._cache.save_to_disk()
```

---

## 6. SQL Pipeline 设计

SQL Pipeline 是核心流水线，分为四个阶段：生成 → 校验 → 执行 → 确认。

### 6.1 Prompt 模板 (`prompts/templates.py`)

```python
SQL_GENERATION_SYSTEM = """\
You are a PostgreSQL SQL expert. Given a user's natural language question \
and the database schema below, generate a single SELECT statement.

Rules:
- Only generate SELECT statements. Never generate INSERT/UPDATE/DELETE/DDL.
- Use fully qualified table names: schema_name.table_name.
- Use proper JOINs based on the foreign key relationships provided.
- When filtering on ENUM columns, use the exact string values listed.
- Add appropriate WHERE clauses to filter the data as the user intends.
- Always include a LIMIT clause.
- Return ONLY the SQL statement, no explanation.

Database Schema:
{schema_context}
"""

RESULT_VALIDATION_SYSTEM = """\
You are a data analyst. A user asked the following question and we executed \
a SQL query. Review the results and determine if they make sense.

User question: {question}
SQL executed: {sql}
Result: {result_preview}

If the result appears reasonable, respond with: VALID
If the result seems wrong or empty when it shouldn't be, respond with: INVALID
followed by a brief explanation and a suggested corrected SQL.
"""
```

**`schema_context` 的组装逻辑：** 将 `DatabaseProfile` 格式化为可读文本，仅包含相关的表（基于用户问题中的关键词做简单匹配，或全部传入）：

```python
def build_schema_context(profile: DatabaseProfile) -> str:
    lines: list[str] = []

    # 按表组织列信息
    for table in profile.tables:
        cols = [c for c in profile.columns if c.table_name == table.table_name]
        col_defs = []
        for c in cols:
            parts = [f"{c.column_name} {c.data_type}"]
            if not c.is_nullable:
                parts.append("NOT NULL")
            if c.column_comment:
                parts.append(f"-- {c.column_comment}")
            col_defs.append("  " + " ".join(parts))

        lines.append(
            f"TABLE {table.schema_name}.{table.table_name}"
            f" (~{table.row_count} rows):\n"
            + "\n".join(col_defs)
        )

    # 外键关系
    if profile.foreign_keys:
        lines.append("\nForeign Keys:")
        for fk in profile.foreign_keys:
            lines.append(
                f"  {fk.from_schema}.{fk.from_table}({fk.from_column})"
                f" -> {fk.to_schema}.{fk.to_table}({fk.to_column})"
            )

    # ENUM 类型
    for enum in profile.enums:
        lines.append(f"\nENUM {enum.schema_name}.{enum.type_name}: {', '.join(enum.values)}")

    return "\n\n".join(lines)
```

### 6.2 SQL 生成 (`sql/generator.py`)

```python
from openai import AsyncOpenAI


class SQLGenerator:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, question: str, schema_context: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_completion_tokens=2048,
            messages=[
                {"role": "system", "content": SQL_GENERATION_SYSTEM.format(
                    schema_context=schema_context
                )},
                {"role": "user", "content": question},
            ],
        )
        sql = response.choices[0].message.content.strip()
        # 提取 SQL（模型可能用 ```sql ... ``` 包裹）
        return self._extract_sql(sql)

    async def validate_result(
        self, question: str, sql: str, result_preview: str
    ) -> tuple[bool, str | None]:
        """让模型判断结果是否合理。返回 (is_valid, corrected_sql_or_none)。"""
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_completion_tokens=1024,
            messages=[
                {"role": "system", "content": RESULT_VALIDATION_SYSTEM.format(
                    question=question, sql=sql, result_preview=result_preview
                )},
            ],
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("VALID"):
            return True, None
        # 尝试从回复中提取修正后的 SQL
        corrected = self._extract_sql(content)
        return False, corrected

    @staticmethod
    def _extract_sql(text: str) -> str:
        """从可能的 markdown code block 中提取 SQL。"""
        import re
        match = re.search(r"```(?:sql)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()
```

### 6.3 SQL 安全校验 (`sql/validator.py`)

基于 `sqlglot` 的 AST 分析。

```python
import sqlglot
from sqlglot import exp


BLOCKED_FUNCTIONS = frozenset({
    "pg_sleep", "pg_terminate_backend", "pg_cancel_backend",
    "lo_import", "lo_export", "lo_create", "lo_unlink",
    "pg_read_file", "pg_ls_dir", "pg_execute_server_program",
})


class SQLValidationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def validate_and_sanitize(sql: str, max_rows: int = 100) -> str:
    """
    校验并修正 SQL。

    Returns: 修正后的 SQL。
    Raises: SQLValidationError 如果 SQL 不通过安全检查。
    """
    # 1. 解析
    try:
        ast = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError as e:
        raise SQLValidationError(f"SQL parse error: {e}")

    # 2. 必须是 SELECT（WITH...SELECT 也是 exp.Select）
    if not isinstance(ast, exp.Select):
        raise SQLValidationError(
            f"Only SELECT statements are allowed, got {type(ast).__name__}"
        )

    # 3. CTE 中不允许有写操作
    for node in ast.find_all(exp.Insert, exp.Update, exp.Delete):
        raise SQLValidationError(
            f"Write operation found in CTE: {type(node).__name__}"
        )

    # 4. 检查危险函数
    for func in ast.find_all(exp.Func):
        if func.name.lower() in BLOCKED_FUNCTIONS:
            raise SQLValidationError(f"Blocked function: {func.name}")

    # 5. 确保 LIMIT 存在且不超过 max_rows
    limit_node = ast.args.get("limit")
    if limit_node:
        try:
            current = int(str(limit_node.expression))
            if current > max_rows:
                ast = ast.limit(max_rows)
        except (ValueError, AttributeError):
            ast = ast.limit(max_rows)
    else:
        ast = ast.limit(max_rows)

    return ast.sql(dialect="postgres")
```

### 6.4 SQL 执行 (`sql/executor.py`)

```python
import asyncpg


class SQLExecutor:
    def __init__(self, pool: asyncpg.Pool, timeout: int = 30) -> None:
        self._pool = pool
        self._timeout = timeout

    async def execute(self, sql: str) -> QueryResult:
        async with self._pool.acquire() as conn:
            # 只读事务
            async with conn.transaction(readonly=True):
                # 设置语句超时
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self._timeout}s'"
                )
                rows = await conn.fetch(sql)

        columns = list(rows[0].keys()) if rows else []
        return QueryResult(
            columns=columns,
            rows=[dict(r) for r in rows],
            row_count=len(rows),
        )
```

**注意：** `conn.transaction(readonly=True)` 等价于 `BEGIN READ ONLY`，从连接层面保证只读。

### 6.5 Pipeline 编排

```python
class SQLPipeline:
    """编排完整的查询流水线。"""

    def __init__(
        self,
        generator: SQLGenerator,
        executor_factory: Callable[[asyncpg.Pool], SQLExecutor],
        cache: SchemaCache,
        pool_manager: PoolManager,
        default_db: str,
    ) -> None:
        self._generator = generator
        self._executor_factory = executor_factory
        self._cache = cache
        self._pool_manager = pool_manager
        self._default_db = default_db

    async def run(
        self,
        question: str,
        database: str | None = None,
        return_sql: bool = False,
        max_rows: int = 100,
    ) -> QueryResponse:
        db = database or self._default_db
        profile = self._cache.get(db)
        if profile is None:
            raise ValueError(f"database unavailable: {db}")

        # 1. 生成 SQL
        schema_context = build_schema_context(profile)
        raw_sql = await self._generator.generate(question, schema_context)

        # 2. 安全校验 + LIMIT 注入
        try:
            safe_sql = validate_and_sanitize(raw_sql, max_rows=max_rows)
        except SQLValidationError as e:
            return QueryResponse(error=e.reason, sql=raw_sql)

        if return_sql:
            return QueryResponse(sql=safe_sql)

        # 3. 执行
        pool = await self._pool_manager.get(db)
        executor = self._executor_factory(pool)
        try:
            result = await executor.execute(safe_sql)
        except Exception as e:
            return QueryResponse(error=f"query execution failed: {e}", sql=safe_sql)

        # 4. 结果确认（空结果时触发）
        if result.row_count == 0:
            preview = "(empty result set)"
            is_valid, corrected_sql = await self._generator.validate_result(
                question, safe_sql, preview
            )
            if not is_valid and corrected_sql:
                try:
                    corrected_sql = validate_and_sanitize(corrected_sql, max_rows)
                    result = await executor.execute(corrected_sql)
                    safe_sql = corrected_sql
                except Exception:
                    pass  # 重试失败，返回原始空结果

        # 5. 组装返回
        return QueryResponse(
            sql=safe_sql,
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
        )
```

---

## 7. MCP Server 设计 (`server.py`)

### 7.1 FastMCP 实例与 Tool 注册

```python
from typing import Annotated
from pydantic import Field
from fastmcp import FastMCP

mcp = FastMCP(
    name="pg-mcp",
    instructions="PostgreSQL query service. Use natural language to query databases.",
    version="0.1.0",
)


# ---- 全局状态 ----

_pool_manager: PoolManager
_cache: SchemaCache
_pipeline: SQLPipeline


# ---- Lifecycle ----

async def _startup() -> None:
    global _pool_manager, _cache, _pipeline

    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings.pg_mcp_log_level)

    # 初始化连接池
    _pool_manager = PoolManager()
    dsn_list = [d.strip() for d in settings.pg_mcp_databases.split(",")]
    await _pool_manager.initialize(dsn_list)

    # 发现并缓存 schema
    _cache = SchemaCache(cache_path=settings.pg_mcp_schema_cache_path)
    discoverer = SchemaDiscoverer(_pool_manager, _cache)
    await discoverer.discover_all(skip_existing=True)

    # 初始化 pipeline
    openai_client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    generator = SQLGenerator(openai_client, settings.openai_model)
    default_db = settings.pg_mcp_default_db or _pool_manager.default_database

    _pipeline = SQLPipeline(
        generator=generator,
        executor_factory=lambda pool: SQLExecutor(pool, settings.pg_mcp_query_timeout),
        cache=_cache,
        pool_manager=_pool_manager,
        default_db=default_db,
    )


async def _shutdown() -> None:
    await _pool_manager.close()


# ---- Tools ----

@mcp.tool
async def query(
    question: Annotated[str, "Natural language description of the data you want to query"],
    database: Annotated[str | None, "Target database name"] = None,
    return_sql: Annotated[bool, "If true, return SQL only; if false, return query results"] = False,
    max_rows: Annotated[int, "Maximum rows to return (1-1000)"] = 100,
) -> dict:
    """Query PostgreSQL database using natural language."""
    return await _pipeline.run(
        question=question,
        database=database,
        return_sql=return_sql,
        max_rows=max_rows,
    )


@mcp.tool
async def list_databases() -> list[dict]:
    """List all accessible databases with summary info."""
    results = []
    for name, profile in _cache.all_profiles().items():
        results.append({
            "database": name,
            "schemas": profile.schemas,
            "table_count": len(profile.tables),
            "view_count": len(profile.views),
        })
    return results


@mcp.tool
async def describe_database(
    database: Annotated[str, "Database name to inspect"],
    schema: Annotated[str | None, "Filter by schema name"] = None,
    pattern: Annotated[str | None, "Filter table/view names by pattern"] = None,
) -> dict:
    """Get detailed schema info for a database."""
    profile = _cache.get(database)
    if profile is None:
        raise ValueError(f"database unavailable: {database}")

    # 按参数过滤
    filtered = filter_profile(profile, schema=schema, pattern=pattern)
    return filtered.model_dump()


@mcp.tool
async def refresh_schema(
    database: Annotated[str | None, "Database to refresh; omit for all"] = None,
) -> dict:
    """Reload schema cache from the database."""
    refreshed, failed = [], []
    targets = [database] if database else _pool_manager.available_databases()
    for db_name in targets:
        try:
            pool = await _pool_manager.get(db_name)
            inspector = SchemaInspector(pool)
            profile = await inspector.collect()
            profile.database_name = db_name
            _cache.put(profile)
            refreshed.append(db_name)
        except Exception as e:
            logger.error("schema_refresh_failed", db=db_name, error=str(e))
            failed.append(db_name)

    _cache.save_to_disk()
    return {"refreshed": refreshed, "failed": failed}


# ---- 入口 ----

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 7.2 Lifecycle 集成方案

FastMCP 的 `on_initialize` middleware 用于执行 `_startup()`，将连接池初始化和 schema 发现放在客户端连接建立时触发：

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext


class LifecycleMiddleware(Middleware):
    async def on_initialize(self, context: MiddlewareContext, call_next):
        await _startup()
        result = await call_next(context)
        await _shutdown()
        return result


mcp.add_middleware(LifecycleMiddleware())
```

---

## 8. Pydantic 响应模型

统一 Tool 返回值结构：

```python
class QueryResponse(BaseModel):
    sql: str
    explanation: str | None = None
    columns: list[str] | None = None
    rows: list[dict] | None = None
    row_count: int | None = None
    error: str | None = None


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict]
    row_count: int
```

---

## 9. 日志设计

使用 `structlog` 输出结构化日志到 stderr（stdout 被 MCP stdio 占用）：

```python
import structlog
import sys


def setup_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
```

每次 query 调用记录：
```
2026-04-13T10:00:00 [info] question="top 10 customers" sql="SELECT ..." elapsed_ms=234 row_count=10 success=true
```

---

## 10. 安全设计汇总

| 防线 | 层 | 机制 |
|------|---|------|
| SQL 类型白名单 | `sql/validator.py` | `sqlglot` AST 校验，仅允许 `exp.Select` |
| CTE 写操作拦截 | `sql/validator.py` | `ast.find_all(exp.Insert, exp.Update, exp.Delete)` |
| 危险函数黑名单 | `sql/validator.py` | `BLOCKED_FUNCTIONS` 集合匹配 |
| 结果集大小限制 | `sql/validator.py` | `sqlglot` AST 注入 LIMIT |
| 只读事务 | `sql/executor.py` | `conn.transaction(readonly=True)` |
| 语句超时 | `sql/executor.py` | `SET LOCAL statement_timeout` |
| 密码脱敏 | `db/pool.py` | 日志中不输出完整 DSN，仅输出数据库名 |
| 错误信息过滤 | `server.py` | `mask_error_details=True`（FastMCP 配置） |

---

## 11. 错误处理设计

所有错误通过 `QueryResponse(error=...)` 返回，不抛出未捕获异常：

| 阶段 | 错误 | 返回内容 |
|------|------|---------|
| Schema 查找 | database 不可用 | `error: "database unavailable: {name}"` |
| OpenAI 调用 | API 错误 | `error: "failed to generate SQL: {detail}"` |
| SQL 校验 | 非只读 / 危险函数 | `error: "{reason}", sql: "<原始生成 SQL>"` |
| SQL 执行 | 超时 | `error: "query execution failed: timeout"` |
| SQL 执行 | 数据库报错 | `error: "query execution failed: {pg_error}"` |
| 结果确认 | 空结果 | 返回实际结果 + 附带 `explanation` 提示 |

---

## 12. 启动流程

```
1. 读取配置 (Settings → 环境变量 / .env)
      │
2. 初始化连接池 (PoolManager.initialize)
      │  └─ 每个 DSN 创建 asyncpg.Pool，失败则跳过
      │
3. 加载 schema 缓存
      │  ├─ 尝试从磁盘加载 (SchemaCache.load_from_disk)
      │  └─ 对未命中缓存或无磁盘缓存的库，执行全量采集
      │
4. 持久化缓存 (SchemaCache.save_to_disk)
      │
5. 启动 FastMCP stdio server
         │
         ▼
    等待 MCP 客户端连接
```

---

## 13. 客户端配置示例

Claude Desktop `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "pg-mcp": {
      "command": "python",
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
