import structlog

from pg_mcp.db.inspector import SchemaInspector
from pg_mcp.db.pool import PoolManager
from pg_mcp.schema.cache import SchemaCache

logger = structlog.get_logger(__name__)


class SchemaDiscoverer:
    def __init__(self, pool_manager: PoolManager, cache: SchemaCache) -> None:
        self._pool_manager = pool_manager
        self._cache = cache

    async def discover_all(self, skip_existing: bool = False) -> None:
        disk_loaded = self._cache.load_from_disk()

        for db_name in self._pool_manager.available_databases():
            if skip_existing and db_name in disk_loaded:
                logger.info("schema_loaded_from_cache", db=db_name)
                continue

            pool = await self._pool_manager.get(db_name)
            inspector = SchemaInspector(pool)
            try:
                profile = await inspector.collect()
                profile.database_name = db_name
                self._cache.put(profile)
                logger.info(
                    "schema_discovered",
                    db=db_name,
                    tables=len(profile.tables),
                    views=len(profile.views),
                )
            except Exception as e:
                logger.error("schema_discover_failed", db=db_name, error=str(e))

        self._cache.save_to_disk()
