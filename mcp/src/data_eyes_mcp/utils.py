"""
Utility functions for Data Eyes MCP Server.

Provides formatting, pagination, and result set handling helpers.
"""

import json
from typing import List, Tuple, Any, Dict


def format_table(headers: List[str], rows: List[Tuple[Any, ...]]) -> str:
    """
    Format table data as ASCII table.

    Args:
        headers: Column names
        rows: List of row tuples

    Returns:
        Formatted ASCII table string
    """
    if not headers:
        return "(no columns)"

    if not rows:
        return "(no rows)"

    # Convert all values to strings and calculate widths
    str_rows = []
    widths = [len(h) for h in headers]

    for row in rows:
        str_row = []
        for i, cell in enumerate(row):
            if cell is None:
                s = "NULL"
            elif isinstance(cell, bool):
                s = "true" if cell else "false"
            elif isinstance(cell, (bytes, bytearray)):
                s = "<binary>"
            else:
                s = str(cell)
            str_row.append(s)
            widths[i] = max(widths[i], len(s))
        str_rows.append(str_row)

    # Build table
    sep = " | "
    header_row = sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))
    divider = "-+-".join("-" * w for w in widths)
    body = []
    for row in str_rows:
        body.append(sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    return "\n".join([header_row, divider] + body)


def rows_to_dicts(headers: List[str], rows: List[Tuple[Any, ...]]) -> List[Dict[str, Any]]:
    """Convert (headers, rows) into a list of JSON-friendly dicts.

    Datetimes are ISO-formatted and binary values shown as "<binary>".
    """
    result: List[Dict[str, Any]] = []
    for row in rows:
        obj: Dict[str, Any] = {}
        for i, header in enumerate(headers):
            value = row[i] if i < len(row) else None
            if isinstance(value, (bytes, bytearray)):
                obj[header] = "<binary>"
            elif hasattr(value, "isoformat"):  # datetime
                obj[header] = value.isoformat()
            else:
                obj[header] = value
        result.append(obj)
    return result


def format_json(headers: List[str], rows: List[Tuple[Any, ...]]) -> str:
    """
    Format table data as a JSON array of objects.

    Args:
        headers: Column names
        rows: List of row tuples

    Returns:
        JSON string with array of objects
    """
    return json.dumps(rows_to_dicts(headers, rows), indent=2, default=str)


def format_csv(headers: List[str], rows: List[Tuple[Any, ...]]) -> str:
    """
    Format table data as CSV.

    Args:
        headers: Column names
        rows: List of row tuples

    Returns:
        CSV formatted string
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow(headers)

    # Write rows
    for row in rows:
        str_row = []
        for cell in row:
            if cell is None:
                str_row.append("")
            elif isinstance(cell, (bytes, bytearray)):
                str_row.append("<binary>")
            elif hasattr(cell, "isoformat"):  # datetime
                str_row.append(cell.isoformat())
            else:
                str_row.append(str(cell))
        writer.writerow(str_row)

    return output.getvalue()


def paginate_results(
    rows: List[Tuple[Any, ...]],
    page: int = 1,
    per_page: int = 100,
) -> Tuple[List[Tuple[Any, ...]], Dict[str, Any]]:
    """
    Paginate results.

    Args:
        rows: All rows
        page: Page number (1-indexed)
        per_page: Results per page

    Returns:
        Tuple of (paginated_rows, pagination_info)
    """
    total = len(rows)
    start = (page - 1) * per_page
    end = start + per_page

    paginated = rows[start:end]
    total_pages = (total + per_page - 1) // per_page

    return paginated, {
        "total_rows": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def escape_sql_identifier(identifier: str) -> str:
    """
    Escape SQL identifier (table name, column name, etc.).
    Uses brackets for SQL Server.

    Args:
        identifier: Identifier to escape

    Returns:
        Escaped identifier
    """
    # SQL Server uses square brackets
    if not identifier:
        return "[]"
    # Replace ] with ]] (escape existing brackets)
    escaped = identifier.replace("]", "]]")
    return f"[{escaped}]"


def escape_sql_string(value: str) -> str:
    """
    Escape SQL string literal.

    Args:
        value: String to escape

    Returns:
        Escaped string literal
    """
    # SQL Server uses single quotes, doubled for escaping
    if not value:
        return "''"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def truncate_string(s: str, max_len: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to maximum length.

    Args:
        s: String to truncate
        max_len: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(s) <= max_len:
        return s
    return s[: max_len - len(suffix)] + suffix


def result_summary(headers: List[str], rows: List[Tuple[Any, ...]]) -> str:
    """
    Create a summary of result set.

    Args:
        headers: Column names
        rows: Result rows

    Returns:
        Summary string
    """
    col_count = len(headers)
    row_count = len(rows)
    return f"{row_count} row(s), {col_count} column(s)"
