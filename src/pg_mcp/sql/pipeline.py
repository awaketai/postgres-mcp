from collections.abc import Callable

import structlog
from asyncpg import Pool

from pg_mcp.db.pool import PoolManager
from pg_mcp.models import QueryResponse
from pg_mcp.prompts.templates import build_schema_context
from pg_mcp.schema.cache import SchemaCache
from pg_mcp.sql.executor import SQLExecutor
from pg_mcp.sql.generator import SQLGenerator
from pg_mcp.sql.validator import SQLValidationError, validate_and_sanitize

logger = structlog.get_logger(__name__)


class SQLPipeline:
    def __init__(
        self,
        generator: SQLGenerator,
        executor_factory: Callable[[Pool], SQLExecutor],
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
            return QueryResponse(
                sql="", error=f"database unavailable: {db}"
            )

        # 1. Generate SQL
        try:
            schema_context = build_schema_context(profile)
            raw_sql = await self._generator.generate(question, schema_context)
        except Exception as e:
            logger.error("sql_generation_failed", error=str(e))
            return QueryResponse(
                sql="", error=f"failed to generate SQL: {e}"
            )

        # 2. Validate & sanitize
        try:
            safe_sql = validate_and_sanitize(raw_sql, max_rows=max_rows)
        except SQLValidationError as e:
            return QueryResponse(error=e.reason, sql=raw_sql)

        if return_sql:
            return QueryResponse(sql=safe_sql)

        # 3. Execute
        try:
            pool = await self._pool_manager.get(db)
            executor = self._executor_factory(pool)
            result = await executor.execute(safe_sql)
        except Exception as e:
            logger.error("sql_execution_failed", sql=safe_sql[:120], error=str(e))
            return QueryResponse(
                error=f"query execution failed: {e}", sql=safe_sql
            )

        # 4. Validate result on empty
        if result.row_count == 0:
            try:
                is_valid, corrected_sql = await self._generator.validate_result(
                    question, safe_sql, "(empty result set)"
                )
                if not is_valid and corrected_sql:
                    try:
                        corrected_sql = validate_and_sanitize(
                            corrected_sql, max_rows
                        )
                        result = await executor.execute(corrected_sql)
                        safe_sql = corrected_sql
                    except Exception:
                        pass
            except Exception:
                pass

        logger.info(
            "query_completed",
            question=question[:80],
            sql=safe_sql[:120],
            row_count=result.row_count,
        )

        return QueryResponse(
            sql=safe_sql,
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
        )
