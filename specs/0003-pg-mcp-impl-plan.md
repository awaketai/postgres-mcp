# 实现计划: PostgreSQL MCP Server

> 基于设计文档 `specs/0002-pg-mcp-design.md`，分阶段实现 pg-mcp。

---

## 实现阶段总览

| 阶段 | 名称 | 目标 | 产物 |
|------|------|------|------|
| P0 | 项目骨架 | 搭建项目结构、依赖管理、配置层 | 可安装的空项目 |
| P1 | 数据层 | 连接池管理 + Schema 采集 + 缓存 | 独立可测试的 db/schema 模块 |
| P2 | SQL Pipeline | SQL 生成 / 校验 / 执行 | 独立可测试的 sql 模块 |
| P3 | MCP Server | FastMCP 集成 + Tool 注册 + Lifecycle | 可启动的 stdio MCP 服务 |
| P4 | 测试 & 收尾 | 单元测试 + 集成验证 | 可交付的完整项目 |

---

## P0: 项目骨架

### 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 0.1 | 创建 `pyproject.toml` | `pyproject.toml` | 项目元数据、依赖声明、`[project.scripts]` 入口 |
| 0.2 | 创建包目录结构 | `src/pg_mcp/`, `src/pg_mcp/db/`, `src/pg_mcp/schema/`, `src/pg_mcp/sql/`, `src/pg_mcp/prompts/` | 所有 `__init__.py` |
| 0.3 | 实现配置模型 | `src/pg_mcp/config.py` | `Settings(BaseSettings)` 完整实现，含 `field_validator` |
| 0.4 | 实现日志初始化 | `src/pg_mcp/logging.py` | `setup_logging()` 函数，structlog 配置输出到 stderr |
| 0.5 | 创建 `.env.example` | `.env.example` | 所有配置项的模板与注释 |
| 0.6 | 创建 Pydantic 响应模型 | `src/pg_mcp/models.py` | `QueryResponse`, `QueryResult` |

### pyproject.toml 要点

```toml
[project]
name = "pg-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=2.14",
    "asyncpg>=0.30",
    "sqlglot>=26.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "openai>=1.0",
    "structlog>=24.0",
]

[project.scripts]
pg-mcp = "pg_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 依赖关系

```
config.py → 无外部依赖（仅 pydantic-settings）
models.py → 仅依赖 pydantic
logging.py → 仅依赖 structlog
```

### 验收标准

- `pip install -e .` 成功
- `from pg_mcp.config import Settings` 可导入
- `Settings(pg_mcp_databases="postgresql://localhost/test", openai_api_key="sk-test")` 可实例化

---

## P1: 数据层

### 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 1.1 | Schema 数据模型 | `src/pg_mcp/schema/models.py` | `ColumnInfo`, `TableInfo`, `ViewInfo`, `ForeignKeyInfo`, `EnumTypeInfo`, `IndexInfo`, `DatabaseProfile` |
| 1.2 | 连接池管理 | `src/pg_mcp/db/pool.py` | `DatabasePool` dataclass + `PoolManager` 类（`initialize`, `get`, `close`, `available_databases`） |
| 1.3 | Schema 元信息采集 | `src/pg_mcp/db/inspector.py` | `SchemaInspector` 类，8 个采集方法分别查询 `information_schema` / `pg_catalog` |
| 1.4 | Schema 缓存管理 | `src/pg_mcp/schema/cache.py` | `SchemaCache` 类（内存 `dict` + 可选磁盘 JSON 持久化） |
| 1.5 | Schema 发现编排 | `src/pg_mcp/schema/discover.py` | `SchemaDiscoverer` 类，编排"磁盘加载 → 采集未命中的库 → 持久化"流程 |

### 依赖关系

```
1.1 schema/models.py  ← 无依赖
1.2 db/pool.py        ← 无依赖
1.3 db/inspector.py   ← 依赖 1.1 (models), 1.2 (asyncpg.Pool)
1.4 schema/cache.py   ← 依赖 1.1 (models)
1.5 schema/discover.py ← 依赖 1.2, 1.3, 1.4
```

### 验收标准

- 需要一个可连接的 PostgreSQL 实例进行验证
- `PoolManager.initialize(["postgresql://..."])` 成功创建连接池
- `SchemaInspector.collect()` 返回包含 tables, columns, foreign_keys 的 `DatabaseProfile`
- `SchemaCache` 能序列化到 JSON 文件并重新加载
- 连接失败的单库不影响其他库的加载

### inspector.py 中的 SQL 查询清单

| 方法 | 查询目标 | 关键表 |
|------|---------|--------|
| `_get_schemas` | 用户 schema 列表 | `information_schema.schemata` |
| `_get_tables` | 表名 + 行数估算 | `pg_class` JOIN `pg_namespace` |
| `_get_columns` | 列名、类型、可空、默认值、注释 | `information_schema.columns` + `col_description()` |
| `_get_views` | 视图名 + 定义 | `information_schema.views` |
| `_get_indexes` | 索引名、列、唯一性 | `pg_indexes` 或 `pg_index` JOIN `pg_class` |
| `_get_foreign_keys` | 外键关系 | `information_schema.table_constraints` + `key_column_usage` + `constraint_column_usage` |
| `_get_enum_types` | ENUM 类型的值列表 | `pg_type` JOIN `pg_enum` JOIN `pg_namespace` |
| `_get_row_counts` | 表行数估算 | `pg_class.reltuples`（合并到 `_get_tables` 中） |

---

## P2: SQL Pipeline

### 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 2.1 | Prompt 模板 | `src/pg_mcp/prompts/templates.py` | `SQL_GENERATION_SYSTEM`, `RESULT_VALIDATION_SYSTEM` 常量 + `build_schema_context()` 函数 |
| 2.2 | SQL 安全校验 | `src/pg_mcp/sql/validator.py` | `validate_and_sanitize()` 函数 + `SQLValidationError` + `BLOCKED_FUNCTIONS` |
| 2.3 | SQL 生成器 | `src/pg_mcp/sql/generator.py` | `SQLGenerator` 类（`generate`, `validate_result`, `_extract_sql`） |
| 2.4 | SQL 执行器 | `src/pg_mcp/sql/executor.py` | `SQLExecutor` 类（只读事务 + 超时） |
| 2.5 | Pipeline 编排 | `src/pg_mcp/sql/pipeline.py` | `SQLPipeline` 类（串联 generate → validate → execute → confirm） |

### 依赖关系

```
2.1 prompts/templates.py ← 依赖 1.1 (DatabaseProfile)
2.2 sql/validator.py     ← 依赖 sqlglot（无内部依赖）
2.3 sql/generator.py     ← 依赖 2.1 (templates), openai
2.4 sql/executor.py      ← 依赖 1.2 (asyncpg.Pool), 0.6 (QueryResult)
2.5 sql/pipeline.py      ← 依赖 2.1, 2.2, 2.3, 2.4, 1.4 (SchemaCache)
```

### 验收标准

**validator.py（无需外部依赖，纯函数测试）：**
- `SELECT * FROM t` → 通过，自动追加 LIMIT
- `INSERT INTO t VALUES (1)` → 抛出 `SQLValidationError`
- `SELECT pg_sleep(10)` → 抛出 `SQLValidationError`
- `WITH cte AS (SELECT 1) SELECT * FROM cte` → 通过
- `SELECT * FROM t LIMIT 5000` + `max_rows=100` → LIMIT 被截断为 100

**generator.py（需 mock OpenAI）：**
- 传入 schema context + question → 返回 SQL 字符串
- 模型返回 `` ```sql ... ``` `` 格式 → 正确提取纯 SQL

**executor.py（需 PostgreSQL 实例）：**
- 只读事务内执行 SELECT → 返回 `QueryResult`
- 只读事务内执行 INSERT → 抛出异常
- 超时 SQL → 抛出超时异常

**pipeline.py（集成测试）：**
- 端到端：question → SQL → 校验 → 执行 → QueryResponse
- 空结果时触发 `validate_result` 二次确认

---

## P3: MCP Server

### 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 3.1 | Lifecycle 管理 | `src/pg_mcp/server.py` | `LifecycleMiddleware` 实现，`_startup()` / `_shutdown()` |
| 3.2 | Tool 注册 | `src/pg_mcp/server.py` | 注册 `query`, `list_databases`, `describe_database`, `refresh_schema` 四个 tool |
| 3.3 | describe_database 过滤 | `src/pg_mcp/server.py` | `filter_profile()` 函数，按 schema / pattern 过滤 |
| 3.4 | 入口函数 | `src/pg_mcp/server.py` | `main()` 函数 → `mcp.run(transport="stdio")` |
| 3.5 | 错误处理 | `src/pg_mcp/server.py` | 所有 tool 内 try/except，通过 `QueryResponse(error=...)` 返回 |

### 依赖关系

```
3.x server.py ← 依赖 P0 (config, models, logging), P1 (pool, inspector, cache, discover), P2 (pipeline)
```

### 验收标准

- `python -m pg_mcp.server` 启动后通过 MCP inspector 或 `fastmcp dev` 能看到 4 个 tool
- `list_databases` 返回数据库列表
- `describe_database(database="mydb")` 返回 schema 信息
- `query(question="...", return_sql=True)` 返回 SQL 文本
- `query(question="...", return_sql=False)` 返回查询结果
- `refresh_schema()` 重新加载 schema 并持久化
- 启动时连接失败的数据库不阻塞服务
- OpenAI API 失败时返回可读的错误信息

---

## P4: 测试 & 收尾

### 任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| 4.1 | 测试基础设施 | `tests/conftest.py` | pytest fixtures：mock asyncpg pool、mock OpenAI client、临时 PostgreSQL（或 mock） |
| 4.2 | validator 单元测试 | `tests/test_validator.py` | 覆盖全部校验场景（SELECT/INSERT/DELETE/危险函数/LIMIT 注入/CTE） |
| 4.3 | generator 单元测试 | `tests/test_generator.py` | mock OpenAI 响应，测试 SQL 提取、结果验证 |
| 4.4 | inspector 单元测试 | `tests/test_inspector.py` | 使用真实 PG 或 mock，验证各采集方法的返回结构 |
| 4.5 | server 集成测试 | `tests/test_server.py` | mock 全部外部依赖，验证 4 个 tool 的端到端行为 |
| 4.6 | 端到端验证 | 手动 | 使用 `fastmcp dev` + 真实 PG + 真实 OpenAI 进行完整流程验证 |

### 测试策略

| 模块 | 测试方式 | 需要外部依赖 |
|------|---------|-------------|
| `validator.py` | 纯函数测试 | 否 |
| `generator.py` | mock OpenAI | 否 |
| `executor.py` | mock asyncpg 或真实 PG | 可选 |
| `inspector.py` | 真实 PG 或 mock | 可选 |
| `server.py` | mock 全部 | 否 |

---

## 文件创建顺序

按依赖关系从底向上，实现时严格按照以下顺序：

```
P0 → P1 → P2 → P3 → P4

P0 内部顺序:
  pyproject.toml
  → src/pg_mcp/__init__.py + 所有子目录 __init__.py
  → src/pg_mcp/models.py
  → src/pg_mcp/config.py
  → src/pg_mcp/logging.py
  → .env.example

P1 内部顺序:
  schema/models.py
  → db/pool.py
  → db/inspector.py
  → schema/cache.py
  → schema/discover.py

P2 内部顺序:
  sql/validator.py        (无内部依赖，最先实现)
  → prompts/templates.py
  → sql/generator.py
  → sql/executor.py
  → sql/pipeline.py

P3 内部顺序:
  server.py (一次性完成)

P4 内部顺序:
  tests/conftest.py
  → tests/test_validator.py
  → tests/test_generator.py
  → tests/test_inspector.py
  → tests/test_server.py
```

---

## 实现注意事项

### 需要特别注意的 API 细节

1. **asyncpg `conn.transaction(readonly=True)`**：确认参数名是 `readonly` 而非 `read_only`，asyncpg 文档中事务参数为 `readonly=True`。

2. **sqlglot `ast.limit(n)` builder**：builder 方法返回新 AST，需确认是否原地修改。设计文档中采用了赋值 `ast = ast.limit(n)`，实现时需验证。

3. **FastMCP `on_initialize` middleware**：设计文档中基于当前文档，如果 FastMCP v3 的 lifecycle API 有变化（如改为 lifespan context manager），需要适配。

4. **asyncpg `fetch` 返回的 `Record` 对象**：`record.keys()` 返回列名，`dict(record)` 可转为普通 dict。需确认在空结果集时 `rows[0].keys()` 的安全性。

5. **OpenAI `_extract_sql`**：模型可能返回带分号的 SQL，也可能不带。提取后应去除尾部分号以保持一致性。
