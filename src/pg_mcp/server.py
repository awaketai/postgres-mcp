from typing import Annotated

import structlog
from openai import AsyncOpenAI

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from pg_mcp.config import Settings
from pg_mcp.db.inspector import SchemaInspector
from pg_mcp.db.pool import PoolManager
from pg_mcp.logging import setup_logging
from pg_mcp.schema.cache import SchemaCache
from pg_mcp.schema.discover import SchemaDiscoverer
from pg_mcp.schema.models import DatabaseProfile
from pg_mcp.sql.executor import SQLExecutor
from pg_mcp.sql.generator import SQLGenerator
from pg_mcp.sql.pipeline import SQLPipeline

logger = structlog.get_logger(__name__)

mcp = FastMCP(
    name="pg-mcp",
    instructions="PostgreSQL query service. Use natural language to query databases.",
    version="0.1.0",
)

_pool_manager: PoolManager | None = None
_cache: SchemaCache | None = None
_pipeline: SQLPipeline | None = None


class LifecycleMiddleware(Middleware):
    async def on_initialize(self, context: MiddlewareContext, call_next):
        await _startup()
        result = await call_next(context)
        await _shutdown()
        return result


mcp.add_middleware(LifecycleMiddleware())


async def _startup() -> None:
    global _pool_manager, _cache, _pipeline

    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings.pg_mcp_log_level)

    # Initialize connection pools
    _pool_manager = PoolManager()
    dsn_list = [d.strip() for d in settings.pg_mcp_databases.split(",")]
    await _pool_manager.initialize(dsn_list)

    # Discover and cache schema
    _cache = SchemaCache(cache_path=settings.pg_mcp_schema_cache_path)
    discoverer = SchemaDiscoverer(_pool_manager, _cache)
    await discoverer.discover_all(skip_existing=True)

    # Initialize pipeline
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
    logger.info("pg_mcp_started", databases=_pool_manager.available_databases())


async def _shutdown() -> None:
    if _pool_manager:
        await _pool_manager.close()
        logger.info("pg_mcp_stopped")


def _get_pipeline() -> SQLPipeline:
    if _pipeline is None:
        raise RuntimeError("Server not initialized")
    return _pipeline


def _get_cache() -> SchemaCache:
    if _cache is None:
        raise RuntimeError("Server not initialized")
    return _cache


def _get_pool_manager() -> PoolManager:
    if _pool_manager is None:
        raise RuntimeError("Server not initialized")
    return _pool_manager


def _filter_profile(
    profile: DatabaseProfile,
    schema: str | None = None,
    pattern: str | None = None,
) -> DatabaseProfile:
    tables = profile.tables
    columns = profile.columns
    views = profile.views
    indexes = profile.indexes
    foreign_keys = profile.foreign_keys

    if schema:
        tables = [t for t in tables if t.schema_name == schema]
        columns = [c for c in columns if c.schema_name == schema]
        views = [v for v in views if v.schema_name == schema]
        indexes = [i for i in indexes if i.schema_name == schema]
        foreign_keys = [fk for fk in foreign_keys if fk.from_schema == schema]

    if pattern:
        pat = pattern.lower()
        tables = [t for t in tables if pat in t.table_name.lower()]
        table_names = {(t.schema_name, t.table_name) for t in tables}
        columns = [c for c in columns if (c.schema_name, c.table_name) in table_names]
        views = [v for v in views if pat in v.view_name.lower()]
        indexes = [i for i in indexes if (i.schema_name, i.table_name) in table_names]

    return DatabaseProfile(
        database_name=profile.database_name,
        schemas=profile.schemas,
        tables=tables,
        columns=columns,
        views=views,
        indexes=indexes,
        foreign_keys=foreign_keys,
        enums=profile.enums,
    )


# ---- Tools ----


@mcp.tool
async def query(
    question: Annotated[str, "Natural language description of the data you want to query"],
    database: Annotated[str | None, "Target database name"] = None,
    return_sql: Annotated[bool, "If true, return SQL only; if false, return query results"] = False,
    max_rows: Annotated[int, "Maximum rows to return (1-1000)"] = 100,
) -> dict:
    """Query PostgreSQL database using natural language."""
    pipeline = _get_pipeline()
    response = await pipeline.run(
        question=question,
        database=database,
        return_sql=return_sql,
        max_rows=max_rows,
    )
    return response.model_dump(exclude_none=True)


@mcp.tool
async def list_databases() -> list[dict]:
    """List all accessible databases with summary info."""
    cache = _get_cache()
    results = []
    for name, profile in cache.all_profiles().items():
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
    cache = _get_cache()
    profile = cache.get(database)
    if profile is None:
        raise ValueError(f"database unavailable: {database}")
    filtered = _filter_profile(profile, schema=schema, pattern=pattern)
    return filtered.model_dump()


@mcp.tool
async def refresh_schema(
    database: Annotated[str | None, "Database to refresh; omit for all"] = None,
) -> dict:
    """Reload schema cache from the database."""
    pm = _get_pool_manager()
    cache = _get_cache()
    refreshed: list[str] = []
    failed: list[str] = []
    targets = [database] if database else pm.available_databases()
    for db_name in targets:
        try:
            pool = await pm.get(db_name)
            inspector = SchemaInspector(pool)
            profile = await inspector.collect()
            profile.database_name = db_name
            cache.put(profile)
            refreshed.append(db_name)
        except Exception as e:
            logger.error("schema_refresh_failed", db=db_name, error=str(e))
            failed.append(db_name)
    cache.save_to_disk()
    return {"refreshed": refreshed, "failed": failed}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
