import structlog
from asyncpg import Pool

from pg_mcp.schema.models import (
    ColumnInfo,
    DatabaseProfile,
    EnumTypeInfo,
    ForeignKeyInfo,
    IndexInfo,
    TableInfo,
    ViewInfo,
)

logger = structlog.get_logger(__name__)

_EXCLUDE_SCHEMAS = ("pg_catalog", "information_schema")


class SchemaInspector:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def collect(self) -> DatabaseProfile:
        async with self._pool.acquire() as conn:
            schemas = await self._get_schemas(conn)
            tables = await self._get_tables(conn)
            columns = await self._get_columns(conn)
            views = await self._get_views(conn)
            indexes = await self._get_indexes(conn)
            foreign_keys = await self._get_foreign_keys(conn)
            enums = await self._get_enum_types(conn)
        return DatabaseProfile(
            schemas=schemas,
            tables=tables,
            columns=columns,
            views=views,
            indexes=indexes,
            foreign_keys=foreign_keys,
            enums=enums,
        )

    async def _get_schemas(self, conn) -> list[str]:
        rows = await conn.fetch(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ($1, $2)
              AND schema_name NOT LIKE 'pg_%'
            ORDER BY schema_name
            """,
            *_EXCLUDE_SCHEMAS,
        )
        return [r["schema_name"] for r in rows]

    async def _get_tables(self, conn) -> list[TableInfo]:
        rows = await conn.fetch(
            """
            SELECT
                n.nspname AS schema_name,
                c.relname AS table_name,
                COALESCE(c.reltuples::bigint, 0) AS row_count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r'
              AND n.nspname NOT IN ($1, $2)
              AND n.nspname NOT LIKE 'pg_%'
            ORDER BY n.nspname, c.relname
            """,
            *_EXCLUDE_SCHEMAS,
        )
        return [TableInfo(**dict(r)) for r in rows]

    async def _get_columns(self, conn) -> list[ColumnInfo]:
        rows = await conn.fetch(
            """
            SELECT
                c.table_schema AS schema_name,
                c.table_name,
                c.column_name,
                c.data_type,
                (c.is_nullable = 'YES') AS is_nullable,
                c.column_default,
                col_description(
                    (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                    c.ordinal_position
                ) AS column_comment
            FROM information_schema.columns c
            WHERE c.table_schema NOT IN ($1, $2)
              AND c.table_schema NOT LIKE 'pg_%'
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
            """,
            *_EXCLUDE_SCHEMAS,
        )
        return [ColumnInfo(**dict(r)) for r in rows]

    async def _get_views(self, conn) -> list[ViewInfo]:
        rows = await conn.fetch(
            """
            SELECT
                table_schema AS schema_name,
                table_name AS view_name,
                view_definition AS definition
            FROM information_schema.views
            WHERE table_schema NOT IN ($1, $2)
              AND table_schema NOT LIKE 'pg_%'
            ORDER BY table_schema, table_name
            """,
            *_EXCLUDE_SCHEMAS,
        )
        return [ViewInfo(**dict(r)) for r in rows]

    async def _get_indexes(self, conn) -> list[IndexInfo]:
        rows = await conn.fetch(
            """
            SELECT
                n.nspname AS schema_name,
                t.relname AS table_name,
                i.relname AS index_name,
                pg_get_indexdef(i.oid) AS index_def,
                indisunique AS is_unique
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname NOT IN ($1, $2)
              AND n.nspname NOT LIKE 'pg_%'
            ORDER BY n.nspname, t.relname, i.relname
            """,
            *_EXCLUDE_SCHEMAS,
        )
        results: list[IndexInfo] = []
        for r in rows:
            cols = _parse_index_columns(r["index_def"])
            results.append(IndexInfo(
                schema_name=r["schema_name"],
                table_name=r["table_name"],
                index_name=r["index_name"],
                columns=cols,
                is_unique=r["is_unique"],
            ))
        return results

    async def _get_foreign_keys(self, conn) -> list[ForeignKeyInfo]:
        rows = await conn.fetch(
            """
            SELECT
                tc.constraint_name,
                tc.table_schema AS from_schema,
                kcu.table_name AS from_table,
                kcu.column_name AS from_column,
                ccu.table_schema AS to_schema,
                ccu.table_name AS to_table,
                ccu.column_name AS to_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema NOT IN ($1, $2)
              AND tc.table_schema NOT LIKE 'pg_%'
            ORDER BY tc.constraint_name
            """,
            *_EXCLUDE_SCHEMAS,
        )
        return [ForeignKeyInfo(**dict(r)) for r in rows]

    async def _get_enum_types(self, conn) -> list[EnumTypeInfo]:
        rows = await conn.fetch(
            """
            SELECT
                n.nspname AS schema_name,
                t.typname AS type_name,
                array_agg(e.enumlabel ORDER BY e.enumsortorder) AS values
            FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname NOT IN ($1, $2)
              AND n.nspname NOT LIKE 'pg_%'
            GROUP BY n.nspname, t.typname
            ORDER BY n.nspname, t.typname
            """,
            *_EXCLUDE_SCHEMAS,
        )
        return [EnumTypeInfo(**dict(r)) for r in rows]


def _parse_index_columns(index_def: str) -> list[str]:
    """Extract column expressions from pg_get_indexdef output.

    Handles expression indexes, sort directions, and nested parentheses.
    Example: CREATE INDEX idx ON tbl USING btree (lower(name), created_at DESC)
    """
    paren_start = index_def.find("(", index_def.find("USING") if "USING" in index_def else 0)
    if paren_start == -1:
        paren_start = index_def.find("(")
    paren_end = index_def.rfind(")")
    if paren_start == -1 or paren_end == -1:
        return []
    inner = index_def[paren_start + 1 : paren_end]

    # Handle WHERE clause in partial indexes
    where_pos = inner.upper().find(" WHERE ")
    if where_pos != -1:
        inner = inner[:where_pos]

    # Split on commas that are not inside parentheses
    columns: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in inner:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            columns.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        columns.append("".join(current).strip())

    return [_strip_identifier_quotes(col) for col in columns if col]


def _strip_identifier_quotes(col: str) -> str:
    if col.startswith('"') and col.endswith('"') and "(" not in col:
        return col[1:-1]
    return col
