# table-talk

Read-only SQL access to a SQL Server or Fabric Lakehouse SQL analytics endpoint from Claude Code.

Claude can list schemas, list tables, describe a table, preview rows, and run a `SELECT` query. The server refuses write statements.

## Set the connection (once per project)

Add this to the project file `.claude/settings.local.json`. Then restart Claude Code.

```json
{
  "env": {
    "FABRIC_SQL_ENDPOINT": "<server hostname>",
    "FABRIC_DATABASE": "<database name>"
  }
}
```

If these values are empty, each tool returns these instructions.

## What the plugin installs

| Part | Purpose |
|---|---|
| `sql-explorer-mcp` MCP server | The five read-only tools. Runs through `uv`. |
| SessionStart hook | Installs `uv` and the Azure CLI if missing. Warms the Python environment. Opens `az login` if you are not signed in. |
| `az-login` skill | Signs you in again when a tool fails with an authentication error. |

The first start is slow because `uv` downloads Python and the libraries. If the server shows as disconnected, restart Claude Code.

## Troubleshooting

| What you see | What to do |
|---|---|
| `Setup needed: ... not set` | Add the `env` block above and restart Claude Code. |
| `spawn uv ENOENT` | The hook installs `uv` on the first session. Restart your terminal and Claude Code. |
| Authentication error | Ask Claude to run the `az-login` skill. |
| Cannot reach the SQL endpoint | Check the hostname. Check that your IP is allowed on the server firewall. |

Run `/mcp` to see the server state.
