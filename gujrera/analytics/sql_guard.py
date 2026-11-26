"""Make officer SQL safe before it runs.

Every query, whether from a canned report or written by the LLM, passes here:

1. Parse with sqlglot. Exactly one statement, and it must be a SELECT (or a
   UNION/INTERSECT/EXCEPT of SELECTs, optionally with a WITH clause).
2. No data-changing or schema statements anywhere in the tree, no PRAGMA /
   ATTACH, and only allow-listed functions (so nothing like load_extension).
3. Only the reporting views in ``ANALYTICS_VIEWS`` may be read, unqualified.
   They contain no complainant identity or contact details.
4. A district-scoped officer's views are replaced by filtered subqueries, so
   the scope cannot be escaped by how the question is phrased.
5. The result is wrapped in a row LIMIT.

The checked query then runs on a read-only connection with a time limit
(``execute_readonly``), so even a guard bug cannot change data.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp
from sqlalchemy import Engine, text

from gujrera.db.views import ANALYTICS_VIEWS

ALLOWED_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "round", "abs", "coalesce", "ifnull", "nullif", "lower", "upper",
    "length", "substr", "substring", "trim", "replace", "cast", "strftime", "date", "julianday", "total",
    "group_concat", "groupconcat", "if", "iif", "case", "instr", "printf", "datetime", "timetostr",
    "strtotime", "tsordstodate", "tsordstotimestamp", "datediff", "currentdate", "currenttimestamp", "dateadd", "concat",
    "dpipe", "safedivide", "div", "least", "greatest", "stddev", "variance", "median",
}
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Merge,
    exp.Transaction, exp.Commit, exp.Rollback, exp.Set, exp.Use, exp.Pragma, exp.Into, exp.LoadData,
)


class UnsafeSQL(ValueError):
    """The query was refused; the message says why, in plain words."""


@dataclass
class GuardedSQL:
    sql: str
    views: list[str]
    scoped_to: str | None


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return node.sql_name().lower().replace("_", "")


def guard_sql(sql: str, *, district_scope: str | None = None, max_rows: int = 500) -> GuardedSQL:
    text_sql = (sql or "").strip().rstrip(";").strip()
    if not text_sql:
        raise UnsafeSQL("Empty query.")
    try:
        statements = [s for s in sqlglot.parse(text_sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQL(f"Could not parse the query: {str(exc).splitlines()[0]}") from None
    if len(statements) != 1:
        raise UnsafeSQL("Only one statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise UnsafeSQL("Only SELECT queries are allowed.")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQL(f"{type(node).__name__} is not allowed.")
        if isinstance(node, exp.Func) and not isinstance(node, (exp.Case, exp.Cast, exp.Paren)):
            name = _function_name(node)
            if name not in ALLOWED_FUNCTIONS:
                raise UnsafeSQL(f"Function {name.upper()} is not allowed.")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    views: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if table.args.get("db") or table.args.get("catalog"):
            raise UnsafeSQL("Qualified table names are not allowed.")
        if name in cte_names:
            continue
        if name not in ANALYTICS_VIEWS:
            raise UnsafeSQL(f"Table {table.name} is not available. Use: {', '.join(ANALYTICS_VIEWS)}.")
        views.add(name)
    if not views:
        raise UnsafeSQL("The query must read at least one reporting view.")

    if district_scope:
        def scope(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Table) and node.name.lower() in views and \
                    not isinstance(node.parent, exp.Subquery):
                alias = node.alias_or_name
                inner = exp.select("*").from_(exp.to_table(node.name)).where(
                    exp.EQ(this=exp.column("district"), expression=exp.Literal.string(district_scope)))
                return exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(alias)))
            return node

        tree = tree.transform(scope)

    inner_sql = tree.sql(dialect="sqlite")
    limited = f"SELECT * FROM ({inner_sql}) AS q LIMIT {int(max_rows)}"
    return GuardedSQL(sql=limited, views=sorted(views), scoped_to=district_scope)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    elapsed_ms: float


def execute_readonly(engine: Engine, guarded: GuardedSQL, *, timeout_s: float = 5.0) -> QueryResult:
    """Run a guarded query on a read-only engine with a time limit."""
    started = time.perf_counter()
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        if conn.dialect.name == "sqlite":
            deadline = started + timeout_s
            raw.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 10_000)
        else:
            conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_s * 1000)}"))
        try:
            res = conn.execute(text(guarded.sql))
            columns = list(res.keys())
            rows = [list(r) for r in res.fetchall()]
        finally:
            if conn.dialect.name == "sqlite":
                raw.set_progress_handler(None, 0)
    limit = int(guarded.sql.rsplit("LIMIT", 1)[1])
    return QueryResult(columns, rows, len(rows) >= limit, round((time.perf_counter() - started) * 1000, 1))
