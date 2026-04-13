import pytest

from pg_mcp.db.inspector import _parse_index_columns


class TestParseIndexColumns:
    def test_single_column(self):
        defn = 'CREATE INDEX idx_name ON public.users USING btree (name)'
        assert _parse_index_columns(defn) == ["name"]

    def test_multiple_columns(self):
        defn = 'CREATE INDEX idx_name ON public.orders USING btree (user_id, created_at)'
        assert _parse_index_columns(defn) == ["user_id", "created_at"]

    def test_quoted_columns(self):
        defn = 'CREATE INDEX idx_name ON public.users USING btree ("User Name")'
        assert _parse_index_columns(defn) == ["User Name"]

    def test_no_parens(self):
        assert _parse_index_columns("no parens here") == []

    def test_expression_index(self):
        defn = 'CREATE INDEX idx_name ON public.users USING btree (lower(name))'
        result = _parse_index_columns(defn)
        assert len(result) == 1
        assert "name" in result[0]
