# /// script
# requires-python = ">=3.11,<3.15"
# dependencies = [
#   "mcp>=1.5.0,<2.0.0",
#   "mssql-python>=1.15.0",
#   "azure-identity>=1.17.0",
#   "pydantic>=2.0.0",
# ]
# ///

#!/usr/bin/env python3
"""
MCP Server for Microsoft Fabric Lakehouse.

Provides read-only tools to explore and query tables in a Microsoft Fabric
Lakehouse via its SQL analytics endpoint. Authenticates using Azure AD /
Entra ID through the azure-identity DefaultAzureCredential chain.

Environment variables:
    FABRIC_SQL_ENDPOINT  â€“ SQL analytics endpoint hostname
                           (e.g. <guid>.datawarehouse.fabric.microsoft.com)
    FABRIC_DATABASE      â€“ Lakehouse / database name
                           If either is empty, tools return setup instructions
                           (set them under "env" in the project's
                           .claude/settings.local.json).

    MCP_TRANSPORT       â€“ Transport mode: "stdio" (default, for local use)
                           or "streamable-http" (for Azure App Service).
    PORT                 â€“ HTTP port when using streamable-http transport
                           (default 8000; Azure App Service sets this).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from enum import Enum
from typing import Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    stream=__import__("sys").stderr)
logger = logging.getLogger("sql-explorer")

import mssql_python
from azure.identity import DefaultAzureCredential
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PREVIEW_ROWS = 50
MAX_PREVIEW_ROWS = 1000
MAX_QUERY_ROWS = 5000
QUERY_TIMEOUT_SECONDS = 120
TOKEN_REFRESH_MARGIN_SECONDS = 300   # refresh 5 min before expiry

# SQL keywords that indicate a write / DDL operation
_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|EXEC|EXECUTE|"
    r"GRANT|REVOKE|DENY|BACKUP|RESTORE|INTO)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Response format enum
# ---------------------------------------------------------------------------

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class ListSchemasInput(BaseModel):
    """Input for listing schemas."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable",
    )


class ListTablesInput(BaseModel):
    """Input for listing tables in a schema."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    schema_name: str = Field(
        default="dbo",
        description="Schema name to list tables from (e.g. 'dbo')",
        min_length=1,
        max_length=128,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )


class DescribeTableInput(BaseModel):
    """Input for describing a table's columns and metadata."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    table_name: str = Field(
        ...,
        description="Fully qualified table name (e.g. 'dbo.my_table') or just 'my_table' (defaults to dbo schema)",
        min_length=1,
        max_length=256,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        if _WRITE_KEYWORDS.search(v):
            raise ValueError("Table name contains disallowed SQL keywords")
        return v


class PreviewDataInput(BaseModel):
    """Input for previewing rows from a table."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    table_name: str = Field(
        ...,
        description="Fully qualified table name (e.g. 'dbo.my_table') or just 'my_table'",
        min_length=1,
        max_length=256,
    )
    limit: int = Field(
        default=DEFAULT_PREVIEW_ROWS,
        description="Number of rows to preview",
        ge=1,
        le=MAX_PREVIEW_ROWS,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        if _WRITE_KEYWORDS.search(v):
            raise ValueError("Table name contains disallowed SQL keywords")
        return v


class QueryInput(BaseModel):
    """Input for executing a read-only SQL query."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    sql: str = Field(
        ...,
        description="A read-only SQL SELECT query to execute against the lakehouse",
        min_length=1,
        max_length=10000,
    )
    limit: int = Field(
        default=100,
        description="Maximum number of rows to return",
        ge=1,
        le=MAX_QUERY_ROWS,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )

    @field_validator("sql")
    @classmethod
    def validate_sql_is_readonly(cls, v: str) -> str:
        stripped = v.strip().rstrip(";").strip()
        if _WRITE_KEYWORDS.search(stripped):
            raise ValueError(
                "Only read-only SELECT queries are allowed. "
                "Write, alter, and delete operations are blocked."
            )
        if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
            raise ValueError(
                "Query must start with SELECT or WITH (CTE). "
                "Only read-only queries are allowed."
            )
        return v


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

class _CachingCredential:
    """Wraps an azure-identity credential and caches the token per scope.

    mssql-python calls get_token() on its token_provider every time it opens
    or reuses a connection. ManagedIdentityCredential (used in production)
    already caches in-memory, but AzureCliCredential (used locally via
    `az login`, as part of the DefaultAzureCredential chain) does not â€” it
    shells out to the `az` executable on every call, which costs 1-2 seconds
    per tool call without this cache.
    """

    def __init__(
        self,
        credential: DefaultAzureCredential,
        refresh_margin_seconds: int = TOKEN_REFRESH_MARGIN_SECONDS,
    ):
        self._credential = credential
        self._refresh_margin = refresh_margin_seconds
        self._cached: dict[tuple, Any] = {}
        self._lock = threading.Lock()

    def get_token(self, *scopes: str, **kwargs: Any) -> Any:
        with self._lock:
            token = self._cached.get(scopes)
            if token is None or token.expires_on - time.time() < self._refresh_margin:
                token = self._credential.get_token(*scopes, **kwargs)
                self._cached[scopes] = token
            return token


_credential: Optional[_CachingCredential] = None
_credential_lock = threading.Lock()


def _get_credential() -> _CachingCredential:
    """Return a process-wide, token-caching credential, creating it on first use.

    Reusing a single credential instance avoids Entra ID throttling; a fresh
    instance per call would re-walk the whole credential chain every time.
    """
    global _credential

    with _credential_lock:
        if _credential is None:
            base = DefaultAzureCredential(exclude_interactive_browser_credential=False)
            _credential = _CachingCredential(base)
        return _credential


class ConfigError(Exception):
    """Raised when the Fabric connection settings are missing."""


def _get_connection() -> mssql_python.Connection:
    """Create a new mssql-python connection to the Fabric SQL analytics endpoint."""
    server = os.environ.get("FABRIC_SQL_ENDPOINT", "").strip()
    database = os.environ.get("FABRIC_DATABASE", "").strip()

    missing = [
        name for name, value in
        (("FABRIC_SQL_ENDPOINT", server), ("FABRIC_DATABASE", database))
        if not value
    ]
    if missing:
        raise ConfigError(
            "Setup needed: " + " and ".join(missing) + " "
            + ("is" if len(missing) == 1 else "are") + " not set.\n\n"
            "To connect, add the values to the project file "
            ".claude/settings.local.json (or .claude/settings.json):\n\n"
            "{\n"
            '  "env": {\n'
            '    "FABRIC_SQL_ENDPOINT": "<guid>.datawarehouse.fabric.microsoft.com",\n'
            '    "FABRIC_DATABASE": "<lakehouse-db>"\n'
            "  }\n"
            "}\n\n"
            "Then restart Claude Code. Find the endpoint in Fabric: "
            "Lakehouse > SQL analytics endpoint > Server."
        )

    connection_string = (
        f"Server={server},1433;"
        f"Database={database};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )

    conn = mssql_python.connect(
        connection_string,
        token_provider=_get_credential(),
    )
    conn.timeout = QUERY_TIMEOUT_SECONDS
    return conn


def _execute_query(sql: str, params: tuple = ()) -> tuple[list[str], list[list[Any]]]:
    """Execute a SQL query and return (column_names, rows)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return columns, [list(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _serialize_value(v: Any) -> Any:
    """Make a value JSON-serializable."""
    if v is None:
        return None
    if isinstance(v, (int, float, bool, str)):
        return v
    if isinstance(v, bytes):
        return v.hex()
    return str(v)


def _rows_to_dicts(columns: list[str], rows: list[list[Any]]) -> list[dict]:
    return [{col: _serialize_value(val) for col, val in zip(columns, row)} for row in rows]


def _format_table_markdown(columns: list[str], rows: list[list[Any]], title: str = "") -> str:
    """Format query results as a Markdown table."""
    if not columns:
        return "No results returned."

    lines: list[str] = []
    if title:
        lines.append(f"## {title}\n")

    # Header
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")

    # Rows
    for row in rows:
        formatted = [str(_serialize_value(v)) if v is not None else "NULL" for v in row]
        lines.append("| " + " | ".join(formatted) + " |")

    lines.append(f"\n*{len(rows)} row(s) returned.*")
    return "\n".join(lines)


def _format_response(
    columns: list[str],
    rows: list[list[Any]],
    fmt: ResponseFormat,
    title: str = "",
) -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(
            {"columns": columns, "row_count": len(rows), "data": _rows_to_dicts(columns, rows)},
            indent=2,
            default=str,
        )
    return _format_table_markdown(columns, rows, title=title)


def _handle_error(e: Exception) -> str:
    """Produce a helpful, non-leaking error message."""
    if isinstance(e, ConfigError):
        return str(e)
    msg = str(e)
    if "Login failed" in msg or "authentication" in msg.lower():
        return (
            "Error: Authentication failed. Ensure you are logged in via "
            "'az login' or that your Azure credentials are configured. "
            f"Details: {msg}"
        )
    if "Cannot open database" in msg:
        return (
            "Error: Cannot open database. Verify that FABRIC_DATABASE is "
            f"set correctly. Details: {msg}"
        )
    if "server was not found" in msg.lower() or "network" in msg.lower():
        return (
            "Error: Cannot reach the SQL endpoint. Verify FABRIC_SQL_ENDPOINT "
            f"is correct and your network allows the connection. Details: {msg}"
        )
    return f"Error: {type(e).__name__}: {msg}"


# ---------------------------------------------------------------------------
# MCP Server & Tools
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "sql_explorer",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
    stateless_http=True,
)


@mcp.tool(
    name="fabric_list_schemas",
    annotations=ToolAnnotations(
        title="List Lakehouse Schemas",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def fabric_list_schemas(params: ListSchemasInput) -> str:
    """List all schemas available in the Fabric Lakehouse.

    Returns the schema names present in the connected lakehouse database.
    Use this to discover what schemas exist before listing tables.

    Args:
        params (ListSchemasInput): Validated input parameters containing:
            - response_format (ResponseFormat): 'markdown' or 'json' (default: markdown)

    Returns:
        str: Schema names formatted per the requested response_format.
    """
    try:
        sql = (
            "SELECT s.name AS schema_name "
            "FROM sys.schemas s "
            "ORDER BY s.name"
        )
        columns, rows = _execute_query(sql)
        return _format_response(columns, rows, params.response_format, title="Schemas")
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="fabric_list_tables",
    annotations=ToolAnnotations(
        title="List Tables in a Schema",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def fabric_list_tables(params: ListTablesInput) -> str:
    """List all tables and views in a given schema of the Fabric Lakehouse.

    Returns table name, type (BASE TABLE or VIEW), and row count estimate
    for every table/view in the specified schema.

    Args:
        params (ListTablesInput): Validated input parameters containing:
            - schema_name (str): Schema to list tables from (default: 'dbo')
            - response_format (ResponseFormat): 'markdown' or 'json'

    Returns:
        str: Table listing formatted per the requested response_format.
    """
    try:
        sql = (
            "SELECT "
            "  t.TABLE_SCHEMA AS [schema], "
            "  t.TABLE_NAME AS [table_name], "
            "  t.TABLE_TYPE AS [type] "
            "FROM INFORMATION_SCHEMA.TABLES t "
            "WHERE t.TABLE_SCHEMA = ? "
            "ORDER BY t.TABLE_NAME"
        )
        columns, rows = _execute_query(sql, (params.schema_name,))
        if not rows:
            return f"No tables found in schema '{params.schema_name}'. Use fabric_list_schemas to see available schemas."
        return _format_response(
            columns, rows, params.response_format,
            title=f"Tables in '{params.schema_name}'",
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="fabric_describe_table",
    annotations=ToolAnnotations(
        title="Describe Table Columns",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def fabric_describe_table(params: DescribeTableInput) -> str:
    """Get detailed column information for a table in the Fabric Lakehouse.

    Returns column name, data type, max length, nullability, and ordinal
    position for every column in the specified table.

    Args:
        params (DescribeTableInput): Validated input parameters containing:
            - table_name (str): Table name, optionally schema-qualified (e.g. 'dbo.sales')
            - response_format (ResponseFormat): 'markdown' or 'json'

    Returns:
        str: Column details formatted per the requested response_format.
    """
    try:
        schema, table = _parse_table_name(params.table_name)
        sql = (
            "SELECT "
            "  c.COLUMN_NAME AS [column_name], "
            "  c.DATA_TYPE AS [data_type], "
            "  c.CHARACTER_MAXIMUM_LENGTH AS [max_length], "
            "  c.IS_NULLABLE AS [nullable], "
            "  c.COLUMN_DEFAULT AS [default_value], "
            "  c.ORDINAL_POSITION AS [ordinal] "
            "FROM INFORMATION_SCHEMA.COLUMNS c "
            "WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ? "
            "ORDER BY c.ORDINAL_POSITION"
        )
        columns, rows = _execute_query(sql, (schema, table))
        if not rows:
            return (
                f"No columns found for '{params.table_name}'. "
                "Verify the table name and schema are correct. "
                "Use fabric_list_tables to see available tables."
            )
        return _format_response(
            columns, rows, params.response_format,
            title=f"Columns in '{schema}.{table}'",
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="fabric_preview_data",
    annotations=ToolAnnotations(
        title="Preview Table Data",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def fabric_preview_data(params: PreviewDataInput) -> str:
    """Preview the first N rows of a table in the Fabric Lakehouse.

    Returns a quick snapshot of data from the specified table. Useful for
    understanding column contents and data quality before writing queries.

    Args:
        params (PreviewDataInput): Validated input parameters containing:
            - table_name (str): Table name, optionally schema-qualified
            - limit (int): Number of rows to return (1â€“1000, default 50)
            - response_format (ResponseFormat): 'markdown' or 'json'

    Returns:
        str: Row data formatted per the requested response_format.
    """
    try:
        schema, table = _parse_table_name(params.table_name)
        # Use bracket-quoted identifiers to prevent injection
        safe_schema = schema.replace("]", "]]")
        safe_table = table.replace("]", "]]")
        sql = f"SELECT TOP {params.limit} * FROM [{safe_schema}].[{safe_table}]"
        columns, rows = _execute_query(sql)
        if not rows:
            return f"Table '{schema}.{table}' returned no rows."
        return _format_response(
            columns, rows, params.response_format,
            title=f"Preview of '{schema}.{table}' ({len(rows)} rows)",
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="fabric_query",
    annotations=ToolAnnotations(
        title="Run Read-Only SQL Query",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def fabric_query(params: QueryInput) -> str:
    """Execute a read-only SQL SELECT query against the Fabric Lakehouse.

    Runs arbitrary SELECT (or WITH/CTE) queries. Write, alter, and delete
    operations are blocked at the input validation layer. Results are
    capped at the specified row limit.

    Args:
        params (QueryInput): Validated input parameters containing:
            - sql (str): The SELECT query to execute
            - limit (int): Max rows to return (1â€“5000, default 100)
            - response_format (ResponseFormat): 'markdown' or 'json'

    Returns:
        str: Query results formatted per the requested response_format.

    Examples:
        - "SELECT COUNT(*) FROM dbo.sales"
        - "SELECT TOP 10 * FROM dbo.customers WHERE region = 'West'"
        - "WITH cte AS (SELECT ...) SELECT * FROM cte"
    """
    try:
        # Wrap the user query with a TOP limit if not already present
        sql = params.sql.strip().rstrip(";")
        columns, rows = _execute_query(sql)

        # Enforce row limit
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            note = f"\n\n*Results truncated to {params.limit} rows.*"
        else:
            note = ""

        result = _format_response(columns, rows, params.response_format, title="Query Results")
        return result + note
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _parse_table_name(table_name: str) -> tuple[str, str]:
    """Parse 'schema.table' or 'table' into (schema, table)."""
    # Remove bracket quoting if present
    cleaned = table_name.replace("[", "").replace("]", "")
    parts = cleaned.split(".", maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "dbo", parts[0].strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower().strip()
    logger.info("Transport mode: '%s'", transport)

    if transport in ("http", "streamable-http"):
        import uvicorn

        # Extract the ASGI app from FastMCP (Starlette app with /mcp route)
        mcp_asgi_app = mcp.streamable_http_app()
        logger.info("Obtained MCP ASGI app from FastMCP")

        # Check whether OAuth env vars are configured
        has_oauth = all(
            os.environ.get(v)
            for v in ("ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_TENANT_ID")
        )

        if has_oauth:
            from oauth_provider import create_oauth_app
            app = create_oauth_app(mcp_asgi_app)
            logger.info("OAuth layer enabled â€” Entra ID authentication required")
        else:
            app = mcp_asgi_app
            logger.warning(
                "OAuth env vars not set â€” running WITHOUT authentication. "
                "Set ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, and "
                "ENTRA_TENANT_ID to enable OAuth."
            )

        host = "0.0.0.0"
        port = int(os.environ.get("PORT", "8000"))
        logger.info("Starting uvicorn on %s:%s", host, port)
        uvicorn.run(app, host=host, port=port)
    else:
        logger.info("Running in stdio mode")
        mcp.run()
