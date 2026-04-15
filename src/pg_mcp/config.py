from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # 数据库
    pg_mcp_databases: str = Field(
        description="Comma-separated PostgreSQL connection strings",
    )
    pg_mcp_default_db: str | None = Field(
        default=None,
        description="Default database name; uses the first DSN if omitted",
    )

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None

    # 查询行为
    pg_mcp_query_timeout: int = Field(default=30, ge=1, le=300)
    pg_mcp_max_rows: int = Field(default=100, ge=1, le=1000)

    # Schema 管理
    pg_mcp_schema_refresh_interval: int = Field(
        default=0,
        description="Auto-refresh interval in seconds; 0 means disabled",
    )
    pg_mcp_schema_cache_path: str | None = Field(
        default=None,
        description="Path for persistent schema cache; memory-only if omitted",
    )

    # 日志
    pg_mcp_log_level: str = Field(default="INFO")

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
    }

    @field_validator("pg_mcp_databases")
    @classmethod
    def validate_dsn_list(cls, v: str) -> str:
        dsns = [d.strip() for d in v.split(",") if d.strip()]
        if not dsns:
            raise ValueError("At least one database connection string is required")
        return v
