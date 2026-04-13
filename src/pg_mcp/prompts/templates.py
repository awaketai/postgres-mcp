from pg_mcp.schema.models import DatabaseProfile

SQL_GENERATION_SYSTEM = """\
You are a PostgreSQL SQL expert. Given a user's natural language question \
and the database schema below, generate a single SELECT statement.

Rules:
- Only generate SELECT statements. Never generate INSERT/UPDATE/DELETE/DDL.
- Use fully qualified table names: schema_name.table_name.
- Use proper JOINs based on the foreign key relationships provided.
- When filtering on ENUM columns, use the exact string values listed.
- Add appropriate WHERE clauses to filter the data as the user intends.
- Always include a LIMIT clause.
- Return ONLY the SQL statement, no explanation.

Database Schema:
{schema_context}
"""

RESULT_VALIDATION_SYSTEM = """\
You are a data analyst. A user asked the following question and we executed \
a SQL query. Review the results and determine if they make sense.

User question: {question}
SQL executed: {sql}
Result: {result_preview}

If the result appears reasonable, respond with: VALID
If the result seems wrong or empty when it shouldn't be, respond with: INVALID
followed by a brief explanation and a suggested corrected SQL.
"""


def build_schema_context(profile: DatabaseProfile) -> str:
    lines: list[str] = []

    for table in profile.tables:
        cols = [
            c for c in profile.columns
            if c.table_name == table.table_name
            and c.schema_name == table.schema_name
        ]
        col_defs = []
        for c in cols:
            parts = [f"{c.column_name} {c.data_type}"]
            if not c.is_nullable:
                parts.append("NOT NULL")
            if c.column_comment:
                parts.append(f"-- {c.column_comment}")
            col_defs.append("  " + " ".join(parts))

        lines.append(
            f"TABLE {table.schema_name}.{table.table_name}"
            f" (~{table.row_count} rows):\n"
            + "\n".join(col_defs)
        )

    for view in profile.views:
        lines.append(
            f"VIEW {view.schema_name}.{view.view_name}:\n"
            f"  {view.definition}"
        )

    if profile.foreign_keys:
        lines.append("\nForeign Keys:")
        for fk in profile.foreign_keys:
            lines.append(
                f"  {fk.from_schema}.{fk.from_table}({fk.from_column})"
                f" -> {fk.to_schema}.{fk.to_table}({fk.to_column})"
            )

    for enum in profile.enums:
        lines.append(
            f"\nENUM {enum.schema_name}.{enum.type_name}:"
            f" {', '.join(enum.values)}"
        )

    return "\n\n".join(lines)
