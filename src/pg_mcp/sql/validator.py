import sqlglot
from sqlglot import exp

BLOCKED_FUNCTIONS = frozenset({
    # Process/session control
    "pg_sleep",
    "pg_terminate_backend",
    "pg_cancel_backend",
    # Large objects
    "lo_import",
    "lo_export",
    "lo_create",
    "lo_unlink",
    # Filesystem access
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_ls_logdir",
    "pg_ls_waldir",
    "pg_ls_tmpdir",
    "pg_stat_file",
    "pg_execute_server_program",
    # Session/config manipulation
    "set_config",
    "pg_reload_conf",
    # Advisory locks (session-level side effects)
    "pg_advisory_lock",
    "pg_advisory_lock_shared",
    "pg_advisory_xact_lock",
    "pg_advisory_xact_lock_shared",
    "pg_try_advisory_lock",
    "pg_try_advisory_lock_shared",
    "pg_try_advisory_xact_lock",
    "pg_try_advisory_xact_lock_shared",
    "pg_advisory_unlock",
    "pg_advisory_unlock_shared",
    "pg_advisory_unlock_all",
    # dblink (remote execution)
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "dblink_connect_u",
    "dblink_disconnect",
    "dblink_send_query",
    "dblink_get_result",
    # Notification side effects
    "pg_notify",
    # Sequence mutation
    "setval",
    "nextval",
    # Copy/export
    "pg_copy_to",
    "pg_copy_from",
})


class SQLValidationError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def validate_and_sanitize(sql: str, max_rows: int = 100) -> str:
    try:
        ast = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.errors.ParseError as e:
        raise SQLValidationError(f"SQL parse error: {e}")

    if not isinstance(ast, exp.Select):
        raise SQLValidationError(
            f"Only SELECT statements are allowed, got {type(ast).__name__}"
        )

    for node in ast.find_all(exp.Insert, exp.Update, exp.Delete):
        raise SQLValidationError(
            f"Write operation found in CTE: {type(node).__name__}"
        )

    for func in ast.find_all(exp.Func):
        if func.name.lower() in BLOCKED_FUNCTIONS:
            raise SQLValidationError(f"Blocked function: {func.name}")

    limit_node = ast.args.get("limit")
    needs_limit = True
    if limit_node:
        try:
            limit_expr = limit_node.expression
            current = int(str(limit_expr))
            if current > max_rows:
                ast = ast.limit(max_rows)
            else:
                needs_limit = False
        except (ValueError, AttributeError):
            pass
    if needs_limit and not limit_node:
        ast = ast.limit(max_rows)

    return ast.sql(dialect="postgres")
