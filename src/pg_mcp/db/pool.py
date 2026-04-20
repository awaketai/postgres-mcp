import structlog
from asyncpg import Pool, create_pool
from dataclasses import dataclass

logger = structlog.get_logger(__name__)

_EXCLUDE_SCHEMAS = frozenset({"pg_catalog", "information_schema"})


@dataclass
class DatabasePool:
    name: str
    dsn: str
    pool: Pool


class PoolManager:
    def __init__(self) -> None:
        self._pools: dict[str, DatabasePool] = {}

    async def initialize(self, dsn_list: list[str]) -> None:
        for dsn in dsn_list:
            name = _resolve_unique_name(dsn, self._pools)
            try:
                pool = await create_pool(
                    dsn,
                    min_size=1,
                    max_size=5,
                    statement_cache_size=0,
                )
                self._pools[name] = DatabasePool(name=name, dsn=dsn, pool=pool)
                logger.info("database_connected", db=name)
            except Exception as e:
                logger.warning("database_connection_failed", db=name, error=str(e))

    async def get(self, database: str) -> Pool:
        entry = self._pools.get(database)
        if entry is None:
            raise ValueError(f"database unavailable: {database}")
        return entry.pool

    async def close(self) -> None:
        for entry in self._pools.values():
            await entry.pool.close()

    def available_databases(self) -> list[str]:
        return list(self._pools.keys())

    @property
    def default_database(self) -> str:
        if not self._pools:
            raise RuntimeError("No databases available — all connections failed")
        return next(iter(self._pools))


def _extract_db_name(dsn: str) -> str:
    # postgresql://user:pass@host:port/dbname?params
    path = dsn.split("/")[-1]
    return path.split("?")[0].strip()


def _extract_host(dsn: str) -> str:
    try:
        after_scheme = dsn.split("@", 1)[1]
        host_port = after_scheme.split("/", 1)[0]
        return host_port.split(":")[0]
    except (IndexError, ValueError):
        return "unknown"


def _resolve_unique_name(dsn: str, existing: dict[str, DatabasePool]) -> str:
    name = _extract_db_name(dsn)
    if name not in existing:
        return name
    host = _extract_host(dsn)
    qualified = f"{name}@{host}"
    if qualified not in existing:
        return qualified
    counter = 2
    while f"{qualified}_{counter}" in existing:
        counter += 1
    return f"{qualified}_{counter}"
