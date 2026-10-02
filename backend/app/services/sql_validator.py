"""Read-only SQL validation using sqlglot."""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel

ALLOWED_ROOTS = (exp.Select, exp.Union)


def validate_sql(sql: str) -> str:
    """Validate that a SQL string is a single read-only SELECT statement.

    Allows SELECT and WITH...SELECT queries (including UNION of selects).
    Rejects empty SQL, syntactically invalid SQL, multi-statement strings,
    and any non-read-only statement (INSERT, UPDATE, DELETE, DROP, ALTER,
    TRUNCATE, CREATE, MERGE, etc.).

    Args:
        sql: SQL string to validate.

    Returns:
        The original SQL string unchanged if validation passes.

    Raises:
        ValueError: If the SQL is empty, invalid, or not read-only.
    """
    if not sql or not sql.strip():
        raise ValueError("Generated SQL is empty")

    try:
        statements = sqlglot.parse(sql, error_level=ErrorLevel.RAISE)
    except Exception as e:
        raise ValueError(f"Generated SQL is invalid: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise ValueError("Generated SQL must contain exactly one statement")

    root = statements[0]
    if not isinstance(root, ALLOWED_ROOTS):
        raise ValueError(
            f"Only read-only SELECT statements are allowed, got {type(root).__name__}"
        )

    return sql


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not nested inside parentheses."""
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def _parse_schema(schema: str) -> dict[str, set[str]]:
    """Extract {table: {columns}} (lowercased) from a schema description.

    Supports CREATE TABLE statements and the shorthand format
    `table(col TYPE, ...)` with one or more tables.
    """
    tables: dict[str, set[str]] = {}

    if re.search(r"\bcreate\s+table\b", schema, re.IGNORECASE):
        try:
            for stmt in sqlglot.parse(schema, error_level=ErrorLevel.RAISE):
                if isinstance(stmt, exp.Create) and isinstance(stmt.this, exp.Schema):
                    tname = stmt.this.this.name.lower()
                    cols = {
                        cd.name.lower()
                        for cd in stmt.this.expressions
                        if isinstance(cd, exp.ColumnDef)
                    }
                    if tname:
                        tables[tname] = cols
        except Exception:
            tables = {}
        if tables:
            return tables

    # Shorthand: table(col TYPE, ...)
    pattern = re.compile(r"(\w+)\s*\(")
    i = 0
    while (m := pattern.search(schema, i)):
        name = m.group(1)
        depth = 1
        j = m.end()
        while j < len(schema) and depth:
            if schema[j] == "(":
                depth += 1
            elif schema[j] == ")":
                depth -= 1
            j += 1
        if depth:  # unbalanced parentheses
            break
        cols = set()
        for part in _split_top_level(schema[m.end() : j - 1]):
            part = part.strip()
            if part:
                col = re.split(r"\s+", part)[0].strip('`"[]')
                if col:
                    cols.add(col.lower())
        tables[name.lower()] = cols
        i = j
    return tables


def validate_sql_against_schema(sql: str, schema: str) -> str:
    """Validate that SQL only references tables/columns present in the schema.

    Supports table aliases, JOINs, CTEs, aggregates, subqueries, and window
    functions. Columns qualified by a CTE or derived-table alias are accepted
    (their underlying tables and columns are validated in their own scope).

    Args:
        sql: SQL string to validate (already read-only per validate_sql).
        schema: The user-provided schema description.

    Returns:
        The original SQL string unchanged if validation passes.

    Raises:
        ValueError: If the schema cannot be parsed, the SQL cannot be
            parsed, or the SQL references unknown tables or columns.
    """
    tables_map = _parse_schema(schema)
    if not tables_map:
        raise ValueError("Could not parse schema into tables and columns")

    try:
        node = sqlglot.parse_one(sql, error_level=ErrorLevel.RAISE)
    except Exception as e:
        raise ValueError(f"Generated SQL is invalid: {e}") from e

    cte_names = {cte.alias.lower() for cte in node.find_all(exp.CTE) if cte.alias}
    derived_aliases = {
        sq.alias.lower() for sq in node.find_all(exp.Subquery) if sq.alias
    }

    schema_columns: set[str] = set()
    for cols in tables_map.values():
        schema_columns |= cols

    query_aliases = {al.alias.lower() for al in node.find_all(exp.Alias) if al.alias}

    # Map qualifiers (table alias or table name) to the referenced table.
    alias_to_table: dict[str, str] = {}
    for tb in node.find_all(exp.Table):
        tname = tb.name.lower()
        alias_to_table[(tb.alias or tb.name).lower()] = tname
        alias_to_table[tname] = tname

    # Every referenced table must be in the schema or be a CTE.
    for tb in node.find_all(exp.Table):
        tname = tb.name.lower()
        if tname in cte_names:
            continue
        if tname not in tables_map:
            raise ValueError(f"Unknown table '{tb.name}' in generated SQL")

    # Every column must resolve to a known table (or known name if unqualified).
    for col in node.find_all(exp.Column):
        is_star = isinstance(col.this, exp.Star)
        cname = col.name.lower()
        qualifier = col.table.lower()

        if not qualifier:
            if is_star:
                continue
            if cname in schema_columns or cname in query_aliases:
                continue
            raise ValueError(f"Unknown column '{col.name}' in generated SQL")

        if qualifier in cte_names or qualifier in derived_aliases:
            continue
        real = alias_to_table.get(qualifier)
        if real is None:
            raise ValueError(
                f"Unknown table '{qualifier}' referenced by column '{col.name}'"
            )
        if real in cte_names:
            continue
        if real not in tables_map:
            raise ValueError(f"Unknown table '{real}' in generated SQL")
        if is_star:
            continue
        if cname not in tables_map[real]:
            raise ValueError(
                f"Unknown column '{col.name}' for table '{real}' in generated SQL"
            )

    return sql
