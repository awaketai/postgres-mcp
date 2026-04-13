import json
from pathlib import Path

import structlog

from pg_mcp.schema.models import DatabaseProfile

logger = structlog.get_logger(__name__)


class SchemaCache:
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

    def save_to_disk(self) -> None:
        if not self._cache_path:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: p.model_dump() for name, p in self._profiles.items()}
        self._cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("schema_cache_saved", path=str(self._cache_path))

    def load_from_disk(self) -> set[str]:
        if not self._cache_path or not self._cache_path.exists():
            return set()
        try:
            data = json.loads(self._cache_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("schema_cache_load_failed", error=str(e))
            return set()

        loaded: set[str] = set()
        for name, profile_data in data.items():
            try:
                self._profiles[name] = DatabaseProfile(**profile_data)
                loaded.add(name)
            except Exception:
                logger.warning("schema_cache_entry_invalid", db=name)
        if loaded:
            logger.info("schema_cache_loaded", count=len(loaded))
        return loaded
