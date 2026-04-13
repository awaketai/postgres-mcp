from unittest.mock import AsyncMock, MagicMock

import pytest

from pg_mcp.models import QueryResponse
from pg_mcp.prompts.templates import build_schema_context
from pg_mcp.schema.cache import SchemaCache
from pg_mcp.server import _filter_profile
from pg_mcp.sql.executor import SQLExecutor
from pg_mcp.sql.pipeline import SQLPipeline


def _make_record(data: dict):
    """Create a mock asyncpg Record that supports keys() and dict()."""
    record = MagicMock()
    record.keys.return_value = list(data.keys())
    record.__iter__ = lambda self: iter(data.items())
    # Support dict(record)
    record.__json__ = lambda: data
    return data  # dict(record) returns the dict itself


class TestBuildSchemaContext:
    def test_includes_tables(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "TABLE public.users" in ctx
        assert "TABLE public.orders" in ctx

    def test_includes_columns(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "id integer" in ctx
        assert "name character varying" in ctx

    def test_includes_column_comments(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "-- user full name" in ctx

    def test_includes_not_null(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "NOT NULL" in ctx

    def test_includes_row_counts(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "~100 rows" in ctx
        assert "~5000 rows" in ctx

    def test_includes_foreign_keys(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "Foreign Keys" in ctx
        assert "public.orders(user_id) -> public.users(id)" in ctx

    def test_includes_enums(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "ENUM public.status_type" in ctx
        assert "active" in ctx

    def test_includes_views(self, sample_profile):
        ctx = build_schema_context(sample_profile)
        assert "VIEW public.active_users" in ctx


class TestFilterProfile:
    def test_no_filter(self, sample_profile):
        result = _filter_profile(sample_profile)
        assert len(result.tables) == 2
        assert len(result.columns) == 5

    def test_filter_by_schema(self, sample_profile):
        result = _filter_profile(sample_profile, schema="public")
        assert len(result.tables) == 2

    def test_filter_by_nonexistent_schema(self, sample_profile):
        result = _filter_profile(sample_profile, schema="nonexistent")
        assert len(result.tables) == 0
        assert len(result.columns) == 0

    def test_filter_by_pattern(self, sample_profile):
        result = _filter_profile(sample_profile, pattern="user")
        assert len(result.tables) == 1
        assert result.tables[0].table_name == "users"
        assert all(c.table_name == "users" for c in result.columns)

    def test_filter_combined(self, sample_profile):
        result = _filter_profile(sample_profile, schema="public", pattern="order")
        assert len(result.tables) == 1
        assert result.tables[0].table_name == "orders"

    def test_enums_not_filtered(self, sample_profile):
        result = _filter_profile(sample_profile, pattern="nonexistent")
        assert len(result.enums) == 1


class TestSQLExecutor:
    async def test_execute_returns_result(self, mock_pool):
        pool, conn = mock_pool
        row = {"id": 1, "name": "Alice"}
        conn.fetch.return_value = [row]

        executor = SQLExecutor(pool, timeout=10)
        result = await executor.execute("SELECT id, name FROM public.users LIMIT 1")
        assert result.row_count == 1
        assert result.columns == ["id", "name"]
        assert result.rows == [{"id": 1, "name": "Alice"}]

    async def test_execute_empty_result(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch.return_value = []

        executor = SQLExecutor(pool, timeout=10)
        result = await executor.execute("SELECT * FROM public.users WHERE 1=0")
        assert result.row_count == 0
        assert result.columns == []

    async def test_execute_sets_timeout(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch.return_value = []

        executor = SQLExecutor(pool, timeout=15)
        await executor.execute("SELECT 1")

        conn.execute.assert_awaited_once()
        call_args = conn.execute.call_args[0][0]
        assert "15s" in call_args
        assert "statement_timeout" in call_args


class TestSQLPipeline:
    @pytest.fixture
    def pipeline_components(self, sample_profile, mock_pool, mock_openai_client):
        pool, conn = mock_pool
        cache = SchemaCache()
        cache.put(sample_profile)

        from pg_mcp.db.pool import PoolManager, DatabasePool
        pm = PoolManager()
        pm._pools["testdb"] = DatabasePool(name="testdb", dsn="postgresql://test", pool=pool)

        from pg_mcp.sql.generator import SQLGenerator
        generator = SQLGenerator(mock_openai_client, "gpt-4o")

        return cache, pm, generator, pool, conn

    async def test_run_returns_sql_only(self, pipeline_components, mock_openai_client):
        cache, pm, generator, pool, conn = pipeline_components

        message = MagicMock()
        message.content = "SELECT id FROM public.users LIMIT 10"
        choice = MagicMock()
        choice.message = message
        mock_openai_client.chat.completions.create.return_value = MagicMock(choices=[choice])

        pipeline = SQLPipeline(
            generator=generator,
            executor_factory=lambda p: SQLExecutor(p, 30),
            cache=cache,
            pool_manager=pm,
            default_db="testdb",
        )
        resp = await pipeline.run("show users", return_sql=True)
        assert isinstance(resp, QueryResponse)
        assert resp.sql != ""
        assert resp.columns is None

    async def test_run_returns_results(self, pipeline_components, mock_openai_client):
        cache, pm, generator, pool, conn = pipeline_components

        message = MagicMock()
        message.content = "SELECT id FROM public.users LIMIT 10"
        choice = MagicMock()
        choice.message = message
        mock_openai_client.chat.completions.create.return_value = MagicMock(choices=[choice])

        conn.fetch.return_value = [{"id": 1}]

        pipeline = SQLPipeline(
            generator=generator,
            executor_factory=lambda p: SQLExecutor(p, 30),
            cache=cache,
            pool_manager=pm,
            default_db="testdb",
        )
        resp = await pipeline.run("show users")
        assert isinstance(resp, QueryResponse)
        assert resp.sql != ""
        assert resp.row_count == 1
        assert resp.columns == ["id"]

    async def test_run_unavailable_database(self, pipeline_components):
        cache, pm, generator, pool, conn = pipeline_components

        pipeline = SQLPipeline(
            generator=generator,
            executor_factory=lambda p: SQLExecutor(p, 30),
            cache=cache,
            pool_manager=pm,
            default_db="testdb",
        )
        resp = await pipeline.run("show users", database="nonexistent")
        assert resp.error is not None
        assert "unavailable" in resp.error

    async def test_run_sql_validation_error(self, pipeline_components, mock_openai_client):
        cache, pm, generator, pool, conn = pipeline_components

        message = MagicMock()
        message.content = "INSERT INTO users (name) VALUES ('test')"
        choice = MagicMock()
        choice.message = message
        mock_openai_client.chat.completions.create.return_value = MagicMock(choices=[choice])

        pipeline = SQLPipeline(
            generator=generator,
            executor_factory=lambda p: SQLExecutor(p, 30),
            cache=cache,
            pool_manager=pm,
            default_db="testdb",
        )
        resp = await pipeline.run("insert a user")
        assert resp.error is not None
        assert "Only SELECT" in resp.error

    async def test_run_openai_failure(self, pipeline_components, mock_openai_client):
        cache, pm, generator, pool, conn = pipeline_components

        mock_openai_client.chat.completions.create.side_effect = Exception("API error")

        pipeline = SQLPipeline(
            generator=generator,
            executor_factory=lambda p: SQLExecutor(p, 30),
            cache=cache,
            pool_manager=pm,
            default_db="testdb",
        )
        resp = await pipeline.run("show users")
        assert resp.error is not None
        assert "failed to generate SQL" in resp.error


class TestSchemaCache:
    def test_put_and_get(self, sample_profile):
        cache = SchemaCache()
        cache.put(sample_profile)
        assert cache.get("testdb") is sample_profile

    def test_get_missing_returns_none(self):
        cache = SchemaCache()
        assert cache.get("nonexistent") is None

    def test_list_databases(self, sample_profile):
        cache = SchemaCache()
        cache.put(sample_profile)
        assert cache.list_databases() == ["testdb"]

    def test_all_profiles(self, sample_profile):
        cache = SchemaCache()
        cache.put(sample_profile)
        profiles = cache.all_profiles()
        assert "testdb" in profiles

    def test_save_and_load_disk(self, sample_profile, tmp_path):
        path = str(tmp_path / "cache.json")
        cache = SchemaCache(cache_path=path)
        cache.put(sample_profile)
        cache.save_to_disk()

        cache2 = SchemaCache(cache_path=path)
        loaded = cache2.load_from_disk()
        assert "testdb" in loaded
        profile = cache2.get("testdb")
        assert profile is not None
        assert len(profile.tables) == 2

    def test_load_disk_missing_file(self, tmp_path):
        cache = SchemaCache(cache_path=str(tmp_path / "nonexistent.json"))
        loaded = cache.load_from_disk()
        assert loaded == set()

    def test_load_disk_invalid_json(self, tmp_path):
        path = tmp_path / "cache.json"
        path.write_text("not json")
        cache = SchemaCache(cache_path=str(path))
        loaded = cache.load_from_disk()
        assert loaded == set()

    def test_save_no_path_is_noop(self, sample_profile):
        cache = SchemaCache()
        cache.put(sample_profile)
        cache.save_to_disk()  # should not raise
