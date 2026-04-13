import pytest

from pg_mcp.sql.validator import SQLValidationError, validate_and_sanitize


class TestStatementTypeCheck:
    def test_select_passes(self):
        sql = "SELECT id, name FROM public.users"
        result = validate_and_sanitize(sql, max_rows=50)
        assert "SELECT" in result
        assert "LIMIT" in result

    def test_select_with_limit_passes(self):
        sql = "SELECT id FROM public.users LIMIT 10"
        result = validate_and_sanitize(sql, max_rows=50)
        assert "LIMIT 10" in result

    def test_insert_rejected(self):
        with pytest.raises(SQLValidationError, match="Only SELECT"):
            validate_and_sanitize("INSERT INTO users (name) VALUES ('test')")

    def test_update_rejected(self):
        with pytest.raises(SQLValidationError, match="Only SELECT"):
            validate_and_sanitize("UPDATE users SET name='x' WHERE id=1")

    def test_delete_rejected(self):
        with pytest.raises(SQLValidationError, match="Only SELECT"):
            validate_and_sanitize("DELETE FROM users WHERE id=1")

    def test_create_table_rejected(self):
        with pytest.raises(SQLValidationError, match="Only SELECT"):
            validate_and_sanitize("CREATE TABLE t (id INT)")

    def test_drop_table_rejected(self):
        with pytest.raises(SQLValidationError, match="Only SELECT"):
            validate_and_sanitize("DROP TABLE users")


class TestCTECheck:
    def test_with_select_passes(self):
        sql = "WITH cte AS (SELECT id FROM public.users) SELECT * FROM cte"
        result = validate_and_sanitize(sql, max_rows=50)
        assert "WITH" in result
        assert "SELECT" in result

    def test_with_insert_rejected(self):
        with pytest.raises(SQLValidationError, match="Only SELECT|Write operation"):
            validate_and_sanitize(
                "WITH cte AS (SELECT id FROM public.users) "
                "INSERT INTO other (id) SELECT id FROM cte"
            )


class TestDangerousFunctions:
    def test_pg_sleep_rejected(self):
        with pytest.raises(SQLValidationError, match="Blocked function"):
            validate_and_sanitize("SELECT pg_sleep(10)")

    def test_lo_import_rejected(self):
        with pytest.raises(SQLValidationError, match="Blocked function"):
            validate_and_sanitize("SELECT lo_import('/etc/passwd')")

    def test_safe_functions_pass(self):
        sql = "SELECT COUNT(*), MAX(id), COALESCE(name, 'N/A') FROM public.users"
        result = validate_and_sanitize(sql, max_rows=50)
        assert "COUNT" in result


class TestLimitInjection:
    def test_limit_injected_when_absent(self):
        sql = "SELECT * FROM public.users"
        result = validate_and_sanitize(sql, max_rows=100)
        assert "LIMIT 100" in result

    def test_limit_capped_when_exceeds_max(self):
        sql = "SELECT * FROM public.users LIMIT 5000"
        result = validate_and_sanitize(sql, max_rows=100)
        assert "LIMIT 100" in result
        assert "5000" not in result

    def test_limit_kept_when_within_max(self):
        sql = "SELECT * FROM public.users LIMIT 10"
        result = validate_and_sanitize(sql, max_rows=100)
        assert "LIMIT 10" in result

    def test_custom_max_rows(self):
        sql = "SELECT * FROM public.users"
        result = validate_and_sanitize(sql, max_rows=25)
        assert "LIMIT 25" in result


class TestParseError:
    def test_invalid_sql_rejected(self):
        with pytest.raises(SQLValidationError, match="SQL parse error"):
            validate_and_sanitize("NOT VALID SQL !!! BROKEN")


class TestComplexQueries:
    def test_join_query_passes(self):
        sql = (
            "SELECT u.name, o.amount FROM public.users u "
            "JOIN public.orders o ON u.id = o.user_id"
        )
        result = validate_and_sanitize(sql, max_rows=50)
        assert "JOIN" in result
        assert "LIMIT" in result

    def test_subquery_passes(self):
        sql = (
            "SELECT * FROM public.users "
            "WHERE id IN (SELECT user_id FROM public.orders)"
        )
        result = validate_and_sanitize(sql, max_rows=50)
        assert "IN" in result

    def test_group_by_passes(self):
        sql = (
            "SELECT user_id, SUM(amount) FROM public.orders "
            "GROUP BY user_id"
        )
        result = validate_and_sanitize(sql, max_rows=50)
        assert "GROUP BY" in result
