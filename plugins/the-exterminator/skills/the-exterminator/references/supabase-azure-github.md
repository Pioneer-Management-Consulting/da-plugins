# Supabase / Azure / GitHub diagnostic checklist

Pioneer's internal tools most often run on Supabase (backend), Azure (hosting/infra), and GitHub (source + CI). When `feature`/`issue` touches this stack, check real state through the tools below rather than inferring it from source files — source files show intent, not what's actually deployed or configured.

## Supabase (use the Supabase MCP tools)

- **Logs first**: `get_logs` for the relevant service (api, postgres, edge functions, auth) often shows the actual error faster than reading code.
- **Advisors**: `get_advisors` (security and performance) — a bug that looks like "the query is wrong" is sometimes "RLS is blocking this" or "there's no index and it's timing out."
- **Migrations**: `list_migrations` — confirm the migration that's supposed to have shipped the relevant schema/policy is actually applied in the environment the bug is happening in. A migration existing in the repo is not evidence it ran.
- **Tables/schema**: `list_tables` to check the live schema matches what the code assumes (column names/types, constraints).
- **RLS policies**: if the symptom is "query works with service role but not from the client" or "user sees no rows / can't write," suspect RLS before suspecting the query.
- **Edge functions**: `list_edge_functions` / `get_edge_function` — check the deployed version and its logs, not just the local source.
- **Secrets/env**: config values referenced by edge functions or the client (e.g. `get_publishable_keys`, `get_project_url`) — confirm the app is pointed at the project/environment you think it is.
- **Branches**: if the project uses Supabase branching, confirm which branch the bug was observed against, and that any fix branch is rebased/merged correctly (`list_branches`, `rebase_branch`, `merge_branch`).

## Azure

- Resource actually provisioned and in the expected region/SKU — "works locally, fails in Azure" is often a resource/config gap, not a code bug.
- App settings / environment variables on the Azure resource match what the code expects (names and values) — a renamed env var in code with no matching update in Azure app settings is a very common silent break.
- Recent deployment history — did the last deploy actually succeed, and does its timestamp line up with when the bug started?
- Networking — firewall rules, private endpoints, CORS at the Azure layer (App Service/Front Door/etc.) can produce failures that look like application bugs.

## GitHub / CI-CD

- Does the deployed artifact match the commit you're reading? Check the CI run tied to the current deployment, not just the latest commit on the branch.
- Did the CI pipeline that deploys secrets/migrations actually run and succeed for the environment in question?
- Repository/Actions secrets — confirm names match what workflows and app config expect; a secret rename in one place without the other is a common source of "works in one environment, not another."

## General principle

Before concluding "this is an application code bug," be able to answer: is this behavior identical across environments (local/staging/prod)? If not, the divergence is almost always config, secrets, migration state, or resource provisioning — not the code itself, since the code is presumably the same across environments.
