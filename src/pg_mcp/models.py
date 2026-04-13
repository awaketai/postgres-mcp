from pydantic import BaseModel


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict]
    row_count: int


class QueryResponse(BaseModel):
    sql: str
    explanation: str | None = None
    columns: list[str] | None = None
    rows: list[dict] | None = None
    row_count: int | None = None
    error: str | None = None
