---
name: az-login
description: Sign in to Azure with the Azure CLI (az logout, then az login). Use when a sql-explorer-mcp tool fails with an authentication error (e.g. "Authentication failed", "DefaultAzureCredential failed to retrieve a token", "Login failed"), or when the user asks to log in to the SQL MCP or to log in to Azure.
---

# Azure login

1. Run `az logout`. Ignore an error that says no account is logged in.
2. Run `az login` with a timeout of 3+ minutes. A browser sign-in window opens. Tell the user to sign in there.
3. Read the terminal output. Tell the user if login succeeded or failed. If it failed, show the exact error.

Run each command as its own call. Do not chain them with `&&` (must work in Bash and PowerShell). Run `az login` once only. If it fails, stop. Do not retry.
