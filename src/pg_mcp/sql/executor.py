import structlog
from asyncpg import Pool

from pg_mcp.models import QueryResult

logger = structlog.get_logger(__name__)


class SQLExecutor:
    def __init__(self, pool: Pool, timeout: int = 30) -> None:
        self._pool = pool
        self._timeout = timeout

    async def execute(self, sql: str) -> QueryResult:
        async with self._pool.acquire() as conn:
            async with conn.transaction(readonly=True):
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
