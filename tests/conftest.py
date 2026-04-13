from unittest.mock import AsyncMock, MagicMock

import pytest

from pg_mcp.schema.models import (
    ColumnInfo,
    DatabaseProfile,
    EnumTypeInfo,
    ForeignKeyInfo,
    IndexInfo,
    TableInfo,
    ViewInfo,
)


@pytest.fixture
def sample_profile() -> DatabaseProfile:
    return DatabaseProfile(
        database_name="testdb",
        schemas=["public"],
        tables=[
            TableInfo(schema_name="public", table_name="users", row_count=100),
            TableInfo(schema_name="public", table_name="orders", row_count=5000),
        ],
        columns=[
            ColumnInfo(
                schema_name="public", table_name="users",
                column_name="id", data_type="integer",
                is_nullable=False,
            ),
            ColumnInfo(
                schema_name="public", table_name="users",
                column_name="name", data_type="character varying",
                is_nullable=True, column_comment="user full name",
            ),
            ColumnInfo(
                schema_name="public", table_name="orders",
                column_name="id", data_type="integer",
                is_nullable=False,
            ),
            ColumnInfo(
                schema_name="public", table_name="orders",
                column_name="user_id", data_type="integer",
                is_nullable=False,
            ),
            ColumnInfo(
                schema_name="public", table_name="orders",
                column_name="amount", data_type="numeric",
                is_nullable=False,
            ),
        ],
        views=[
            ViewInfo(
                schema_name="public",
                view_name="active_users",
                definition="SELECT * FROM public.users WHERE id > 0",
            ),
        ],
        indexes=[
            IndexInfo(
                schema_name="public", table_name="users",
                index_name="users_pkey", columns=["id"], is_unique=True,
            ),
        ],
        foreign_keys=[
            ForeignKeyInfo(
                constraint_name="orders_user_id_fkey",
                from_schema="public", from_table="orders", from_column="user_id",
                to_schema="public", to_table="users", to_column="id",
            ),
        ],
        enums=[
            EnumTypeInfo(
                schema_name="public", type_name="status_type",
                values=["active", "inactive", "suspended"],
            ),
        ],
    )


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()

    # pool.acquire() returns an async context manager yielding conn
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = acquire_cm

    # conn.transaction(readonly=True) returns an async context manager
    # Must use spec to prevent transaction() from being treated as async
    conn.transaction = MagicMock()
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction.return_value = tx_cm

    return pool, conn


@pytest.fixture
def mock_openai_client():
    client = AsyncMock()
    return client
