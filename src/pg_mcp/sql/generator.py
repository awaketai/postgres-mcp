import re

import structlog
from openai import AsyncOpenAI

from pg_mcp.prompts.templates import (
    RESULT_VALIDATION_SYSTEM,
    SQL_GENERATION_SYSTEM,
)

logger = structlog.get_logger(__name__)


class SQLGenerator:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate(self, question: str, schema_context: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_completion_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": SQL_GENERATION_SYSTEM.format(
                        schema_context=schema_context
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        raw = response.choices[0].message.content.strip()
        sql = _extract_sql(raw)
        logger.debug("sql_generated", question=question[:80], sql=sql[:120])
        return sql

    async def validate_result(
        self, question: str, sql: str, result_preview: str
    ) -> tuple[bool, str | None]:
        response = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_completion_tokens=1024,
            messages=[
                {
                    "role": "system",
                    "content": RESULT_VALIDATION_SYSTEM.format(
                        question=question, sql=sql, result_preview=result_preview
                    ),
                },
            ],
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("VALID"):
            return True, None
        corrected = _extract_sql(content)
        return False, corrected


def _extract_sql(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip().rstrip(";")
