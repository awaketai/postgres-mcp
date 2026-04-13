from unittest.mock import MagicMock

import pytest

from pg_mcp.sql.generator import SQLGenerator, _extract_sql


def _mock_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestExtractSQL:
    def test_plain_sql(self):
        assert _extract_sql("SELECT 1") == "SELECT 1"

    def test_sql_in_code_block(self):
        text = "```sql\nSELECT id FROM users\n```"
        assert _extract_sql(text) == "SELECT id FROM users"

    def test_sql_in_code_block_no_language(self):
        text = "```\nSELECT id FROM users\n```"
        assert _extract_sql(text) == "SELECT id FROM users"

    def test_trailing_semicolon_removed(self):
        assert _extract_sql("SELECT 1;") == "SELECT 1"

    def test_whitespace_stripped(self):
        assert _extract_sql("  SELECT 1  ") == "SELECT 1"


class TestSQLGenerator:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.chat.completions.create = pytest.mock_async_method(
            _mock_response("SELECT 1")
        )
        return client

    async def test_generate_returns_sql(self, mock_openai_client):
        mock_openai_client.chat.completions.create.return_value = (
            _mock_response("SELECT id FROM public.users LIMIT 10")
        )
        gen = SQLGenerator(mock_openai_client, "gpt-4o")
        result = await gen.generate("show all users", "schema context here")
        assert "SELECT" in result
        assert "FROM" in result

    async def test_generate_extracts_from_code_block(self, mock_openai_client):
        mock_openai_client.chat.completions.create.return_value = (
            _mock_response("```sql\nSELECT id FROM public.users\n```")
        )
        gen = SQLGenerator(mock_openai_client, "gpt-4o")
        result = await gen.generate("show all users", "schema context here")
        assert result == "SELECT id FROM public.users"

    async def test_validate_result_valid(self, mock_openai_client):
        mock_openai_client.chat.completions.create.return_value = (
            _mock_response("VALID")
        )
        gen = SQLGenerator(mock_openai_client, "gpt-4o")
        is_valid, corrected = await gen.validate_result(
            "show users", "SELECT * FROM users", "(empty result set)"
        )
        assert is_valid is True
        assert corrected is None

    async def test_validate_result_invalid_with_correction(self, mock_openai_client):
        mock_openai_client.chat.completions.create.return_value = (
            _mock_response(
                "INVALID\nThe query may need adjustment.\n"
                "```sql\nSELECT * FROM public.users WHERE active = true\n```"
            )
        )
        gen = SQLGenerator(mock_openai_client, "gpt-4o")
        is_valid, corrected = await gen.validate_result(
            "show active users", "SELECT * FROM users", "(empty result set)"
        )
        assert is_valid is False
        assert corrected is not None
        assert "SELECT" in corrected
