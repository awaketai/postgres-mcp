# PRD: PostgreSQL MCP Server

> 自然语言驱动的 PostgreSQL 查询服务，基于 MCP 协议，通过 OpenAI 生成并执行 SQL。

## 1. 背景与目标

### 1.1 背景

用户希望用自然语言描述查询需求，由系统自动生成 SQL 并返回结果，而非手写 SQL。MCP（Model Context Protocol）作为标准化的工具协议，可以让任意支持 MCP 的客户端（如 Claude Desktop、IDE 插件等）直接调用本服务。

### 1.2 目标

- 提供一个 MCP Server，支持用户以自然语言查询 PostgreSQL 数据库。
- 自动发现并缓存数据库 schema，作为 SQL 生成的上下文。
- 调用 OpenAI 大模型将自然语言翻译为 SQL。
- 对生成的 SQL 进行安全校验和执行验证，确保只读、可执行、结果有意义。
- 根据用户意图返回 SQL 语句或查询结果。

### 1.3 非目标

- 不支持写操作（INSERT / UPDATE / DELETE / DDL 等）。
- 不支持数据库管理（创建/删除数据库、用户权限管理等）。
- 不做多租户权限隔离（初始版本假设使用者拥有目标数据库的只读权限）。

---

## 2. 核心概念

| 概念 | 说明 |
|------|------|
| **MCP Server** | 本服务的主体，通过 MCP 协议对外暴露工具（tools）。 |
| **Database Profile** | 服务启动时为每个可访问数据库建立的 schema 快照，包含表、视图、类型、索引等元信息。 |
| **Schema Cache** | Database Profile 的内存缓存，服务运行期间用于提供 SQL 生成所需的上下文。 |
| **SQL Pipeline** | 自然语言 → OpenAI 生成 SQL → 安全校验 → 执行验证 → 结果确认 → 返回 的完整流水线。 |

---

## 3. 用户故事

### US-1 查询数据库获取结果

> 作为用户，我输入 "上个月销售额最高的前 10 个客户是谁"，服务返回一个包含客户名称和销售额的表格结果。

### US-2 获取 SQL 而非结果

> 作为用户，我输入 "上个月销售额最高的前 10 个客户是谁" 并指定返回 SQL，服务返回一条可执行的 SELECT 语句。

### US-3 交互式纠错

> 作为用户，当生成的 SQL 返回空结果或结果看起来不对时，服务自动进行二次确认或提示我调整描述。

---

## 4. 功能需求

### 4.1 服务启动与 Schema 发现

**FR-4.1.1 数据库连接发现**

- 服务通过配置文件（环境变量 / `.env` / 配置文件）获取一个或多个 PostgreSQL 连接串。
- 启动时逐一连接每个数据库，连接失败则跳过并在日志中记录告警，不阻塞其他数据库的加载。

**FR-4.1.2 Schema 元信息采集**

对每个成功连接的数据库，采集以下信息并缓存：

| 元信息类型 | 具体内容 |
|-----------|---------|
| Schema（命名空间） | schema 名称列表（排除系统 schema：`pg_*`, `information_schema`） |
| 表（Table） | 表名、列名、列类型、是否可空、默认值、注释 |
| 视图（View） | 视图名、列定义、视图定义 SQL |
| 物化视图（Materialized View） | 同视图 |
| 自定义类型（Type） | ENUM 值列表、COMPOSITE 类型字段 |
| 索引（Index） | 索引名、关联表、索引列、唯一性 |
| 外键关系（Foreign Key） | 关联的表和列 |
| 行数估算 | 每张表的近似行数（从 `pg_class.reltuples` 获取） |

**FR-4.1.3 Schema 缓存策略**

- 首次启动时全量加载，缓存到内存。
- 提供 MCP tool 供用户主动刷新缓存（`refresh_schema`）。
- 可选：配置自动刷新间隔（默认关闭）。

### 4.2 MCP Tools 定义

服务对外暴露以下 MCP tools：

#### Tool 1: `query`

**用途：** 用户用自然语言描述查询需求，服务返回查询结果或 SQL。

**入参：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `question` | string | 是 | 用户的自然语言查询描述 |
| `database` | string | 否 | 目标数据库名，不传时使用默认数据库 |
| `return_sql` | boolean | 否 | `true` 返回 SQL 文本，`false`（默认）返回查询结果 |
| `max_rows` | integer | 否 | 返回结果的最大行数，默认 100，上限 1000 |

**出参：**

```
return_sql=true  → { sql: string, explanation: string }
return_sql=false → { sql: string, explanation: string, columns: [...], rows: [...], row_count: number }
```

#### Tool 2: `list_databases`

**用途：** 列出当前服务可访问的所有数据库及其简要信息。

**入参：** 无

**出参：**

```
[
  { database: string, schemas: string[], table_count: number, view_count: number }
]
```

#### Tool 3: `describe_database`

**用途：** 查看某个数据库的详细 schema 信息（表、视图、列、类型等）。

**入参：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `database` | string | 是 | 数据库名 |
| `schema` | string | 否 | 过滤特定 schema，不传则返回全部 |
| `pattern` | string | 否 | 按表名/视图名模糊匹配 |

**出参：** 结构化的 schema 元信息（与 FR-4.1.2 采集内容一致）。

#### Tool 4: `refresh_schema`

**用途：** 重新加载指定数据库（或全部数据库）的 schema 缓存。

**入参：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `database` | string | 否 | 指定刷新某个数据库，不传则刷新全部 |

**出参：** `{ refreshed: string[], failed: string[] }`

### 4.3 SQL 生成流程（SQL Pipeline）

#### FR-4.3.1 自然语言转 SQL

- 将用户的 `question` 与相关 schema 信息（表结构、列注释、外键关系、示例数据等）组装为 prompt。
- 调用 OpenAI Chat Completions API 生成 SQL。
- Prompt 设计要点：
  - 明确要求只生成 SELECT 语句。
  - 包含完整的相关表结构定义（列名、类型、注释）。
  - 包含外键关系以辅助 JOIN 推理。
  - 包含自定义类型的 ENUM 值以辅助条件过滤。
- 可选：包含少量示例行数据（`SELECT ... LIMIT 3`）帮助模型理解数据内容。

#### FR-4.3.2 SQL 安全校验

生成 SQL 后、执行前，必须通过以下检查：

| 检查项 | 规则 | 失败处理 |
|--------|------|---------|
| 语句类型 | 必须为 SELECT 或 WITH...SELECT（通过解析 SQL 的首个关键字判定） | 拒绝执行，返回错误 |
| 危险函数 | 禁止调用 `pg_sleep`、`lo_import`、`lo_export` 等危险函数 | 拒绝执行，返回错误 |
| 结果集大小 | 不允许不带 LIMIT 的查询（自动追加 `LIMIT max_rows`） | 自动修正 |
| 语法正确性 | 通过 `EXPLAIN` 验证 SQL 可被数据库解析 | 返回错误，可选触发重新生成 |

- 校验通过后使用只读连接执行查询。

#### FR-4.3.3 执行验证

- 在只读事务中执行 SQL（`SET TRANSACTION READ ONLY`）。
- 捕获执行异常（超时、权限不足、语法错误等）。
- 设置查询超时（默认 30 秒，可配置）。

#### FR-4.3.4 结果确认（可选）

当查询返回结果为空或结果行数异常少时：

- 将 SQL、用户原始问题、返回结果（或 "空结果" 信息）发送给 OpenAI。
- 让模型判断：结果是否合理，是否需要修改 SQL。
- 如果模型建议修改，则使用修改后的 SQL 重新执行（最多重试 1 次）。

### 4.4 配置管理

**FR-4.4.1 配置来源**

优先级从高到低：环境变量 > `.env` 文件 > 配置文件。

**FR-4.4.2 配置项**

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| 数据库连接串 | `PG_MCP_DATABASES` | 无（必填） | 逗号分隔的连接串，格式：`postgresql://user:pass@host:port/dbname` |
| 默认数据库 | `PG_MCP_DEFAULT_DB` | 列表中第一个 | 默认查询目标 |
| OpenAI API Key | `OPENAI_API_KEY` | 无（必填） | |
| OpenAI 模型 | `OPENAI_MODEL` | `gpt-4o` | |
| OpenAI Base URL | `OPENAI_BASE_URL` | OpenAI 默认 | 支持自定义端点（Azure、代理等） |
| 查询超时 | `PG_MCP_QUERY_TIMEOUT` | `30` | 单位：秒 |
| 最大返回行数 | `PG_MCP_MAX_ROWS` | `100` | 上限 1000 |
| Schema 自动刷新间隔 | `PG_MCP_SCHEMA_REFRESH_INTERVAL` | `0`（关闭） | 单位：秒 |
| 日志级别 | `PG_MCP_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

---

## 5. 非功能需求

### 5.1 安全性

| 编号 | 要求 |
|------|------|
| NFR-S1 | 生成的 SQL 必须通过白名单校验，只允许 SELECT / WITH...SELECT。 |
| NFR-S2 | 使用只读事务执行所有查询，从连接层面杜绝写操作。 |
| NFR-S3 | 数据库连接串中如果包含密码，不得出现在日志、API 返回值或 schema 缓存中。 |
| NFR-S4 | 对生成的 SQL 设置执行超时，防止资源耗尽型查询。 |
| NFR-S5 | 自动为查询追加 LIMIT，防止返回海量结果集。 |

### 5.2 性能

| 编号 | 要求 |
|------|------|
| NFR-P1 | Schema 发现阶段，单个数据库的元信息加载不超过 10 秒。 |
| NFR-P2 | 单次查询端到端延迟（不含 OpenAI 调用）不超过 5 秒。 |
| NFR-P3 | 内存占用与缓存的 schema 数量成正比，单个数据库 schema 缓存不超过 50MB。 |

### 5.3 可靠性

| 编号 | 要求 |
|------|------|
| NFR-R1 | 单个数据库连接失败不影响其他数据库的使用。 |
| NFR-R2 | 单次查询执行失败不影响后续查询。 |
| NFR-R3 | OpenAI API 调用失败时返回明确的错误信息，不暴露内部实现细节。 |

### 5.4 可观测性

| 编号 | 要求 |
|------|------|
| NFR-O1 | 每次查询记录日志：用户问题、生成的 SQL、执行耗时、返回行数、是否成功。 |
| NFR-O2 | Schema 刷新操作记录日志：刷新了哪些数据库、耗时、是否成功。 |

---

## 6. 技术约束

| 约束 | 说明 |
|------|------|
| 语言 | Python 3.11+ |
| MCP SDK | 使用官方 `mcp` Python SDK，仅 stdio transport |
| 数据库驱动 | `asyncpg`（异步）或 `psycopg`（同步），倾向 `asyncpg` 以配合 MCP 的异步模型 |
| OpenAI SDK | `openai` Python SDK |
| SQL 解析 | 使用 `sqlglot` 进行 SQL 语法分析和安全校验 |

---

## 7. 数据流

```
用户（MCP 客户端）
  │
  │  MCP request (question, database, return_sql)
  ▼
MCP Server
  │
  ├─ 1. 根据 database 参数定位 schema cache
  │
  ├─ 2. 组装 prompt = question + relevant schema
  │     ↓
  │     OpenAI API → 生成 SQL
  │
  ├─ 3. 安全校验（SELECT-only、无危险函数、追加 LIMIT）
  │     ↓ 失败 → 返回错误
  │
  ├─ 4. 只读事务中执行 SQL（带超时）
  │     ↓ 失败 → 返回执行错误
  │
  ├─ 5. [可选] 结果确认（空结果时调用 OpenAI 二次校验）
  │
  ├─ 6. 根据 return_sql 参数组装返回内容
  │
  ▼
MCP response → 用户
```

---

## 8. 错误处理

| 场景 | 行为 |
|------|------|
| 数据库连接失败 | 启动时跳过该库并告警；查询时返回 "database unavailable" 错误 |
| OpenAI API 调用失败 | 返回 "failed to generate SQL" 错误，附带错误详情 |
| SQL 安全校验失败 | 返回 "generated SQL failed safety check" 错误，附带具体原因 |
| SQL 执行超时 | 返回 "query timeout" 错误 |
| SQL 执行报错 | 返回 "query execution failed" 错误，附带数据库错误信息 |
| 结果确认为空/不合理 | 返回结果并附加提示说明，不隐藏数据 |

---

## 9. 已确认决策

| 编号 | 决策 |
|------|------|
| Q1 | **不支持多轮对话。** 每次查询独立，不维护对话上下文。 |
| Q2 | **不包含示例数据。** Prompt 中仅包含 schema 元信息（表结构、列名、类型、注释、外键），不采样实际行数据。 |
| Q3 | **不持久化查询历史。** 仅通过日志记录查询信息，不做结构化存储。 |
| Q4 | **仅支持 stdio transport。** 作为客户端子进程运行，通过 stdin/stdout 通信。不支持 SSE。 |
| Q5 | **可选持久化 schema 缓存。** 支持将 schema 缓存序列化到磁盘文件，重启时优先从磁盘加载，可按需跳过重新采集以加速启动。 |
