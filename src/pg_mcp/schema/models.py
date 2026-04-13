from pydantic import BaseModel


class ColumnInfo(BaseModel):
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: str | None = None
    column_comment: str | None = None


class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    row_count: int


class ViewInfo(BaseModel):
    schema_name: str
    view_name: str
    definition: str


class ForeignKeyInfo(BaseModel):
    constraint_name: str
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str


class EnumTypeInfo(BaseModel):
    schema_name: str
    type_name: str
    values: list[str]


class IndexInfo(BaseModel):
    schema_name: str
    table_name: str
    index_name: str
    columns: list[str]
    is_unique: bool


class DatabaseProfile(BaseModel):
    database_name: str = ""
    schemas: list[str]
    tables: list[TableInfo]
    columns: list[ColumnInfo]
    views: list[ViewInfo]
    indexes: list[IndexInfo]
    foreign_keys: list[ForeignKeyInfo]
    enums: list[EnumTypeInfo]
