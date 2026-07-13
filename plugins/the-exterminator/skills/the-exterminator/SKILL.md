---
name: the-exterminator
description: Systematic, evidence-based bug-fixing workflow that takes two arguments, feature and issue, and walks through diagnose, plan, adversarial review, report, approval, execute, verify, in that order. Treats the user's description of a bug as a hypothesis, not a fact, and checks every layer (client code, server/API code, database/migrations, infra and resource config, secrets/env vars, CI/CD) before proposing a fix, instead of editing whatever file the user happened to point at. Use whenever the user reports a bug, error, crash, failing test, unexpected behavior, "this is broken," a regression, or asks to debug/investigate/troubleshoot/fix something — especially when the fix is not obviously a one-line typo. For Pioneer's internal Supabase/Azure/GitHub stack, also load references/supabase-azure-github.md for platform-specific checks. Do not use for greenfield feature work, refactors, or style changes where there is no reported defect.
argument-hint: "[feature] [issue]"
---

# Systematic Bug Fixing

## Why this exists

The most common way bug fixes go wrong is skipping straight from "user says X is broken" to "edit the code near X." That treats the user's framing of the bug as ground truth, when it's really just their best guess from the outside. A wrong guess plus a fast fix produces code that looks more "correct" but doesn't fix anything, or masks the real problem one layer deeper. This skill enforces the discipline that any competent engineer or SRE applies to an unfamiliar incident: gather evidence before forming a theory, form a theory before proposing a change, and stress-test the theory before touching anything.

## Arguments

- `feature` — the feature/area affected (e.g. "checkout flow", "user login MCP tool")
- `issue` — what's actually being observed (symptom, error text, repro steps)

Parse these from however the user invokes the skill — as explicit `feature=... issue=...` arguments, or as free text following the invocation. If either is missing or too vague to act on (e.g. "it's broken"), ask for it before doing any investigation. A wrong or missing argument wastes the whole workflow downstream.

Also ask anything else you genuinely need and can't infer, but don't interrogate — one round of clarifying questions, then proceed. Reasonable things to ask about if unclear: when this last worked, whether it's reproducible or intermittent, whether it happens for all users/environments or just one, and whether anything changed recently (deploy, migration, config, dependency bump).

## Phase 1 — Diagnose

Goal: find the root cause, backed by evidence you actually looked at — not the first plausible story.

**Reproduce or ground the symptom first.** Before reading code, look for direct evidence of what's happening: error logs, stack traces, failing test output, network/response codes, database query results. A theory built on "the user said X" is weaker than one built on "the logs show Y." If you can reproduce the issue (run the failing test, hit the endpoint, run the query), do it.

**Work outward from the symptom across every layer, don't fixate on the layer the user named.** The user pointed you at a `feature`, not necessarily at the cause. Systematically rule layers in or out — for a typical web app + backend, that's roughly:

1. **Client** — UI/state logic, request construction, error handling of the response
2. **Server/API** — route/handler logic, request validation, business logic
3. **Database** — schema, migrations applied vs. pending, RLS/permissions, data itself (bad/missing rows), query correctness
4. **Infra & config** — environment variables, secrets (correct values, correct environment — dev vs. prod), resource provisioning (e.g. wrong region, missing service, scaling limits), networking/CORS
5. **CI/CD & deploy** — is the code that's deployed actually the code you're reading? Did the last deploy succeed? Did a migration get applied in this environment?
6. **Dependencies/third-party** — library version mismatches, breaking changes in an upstream API or SDK

You don't need to exhaustively audit all six for every bug — use the evidence to prune fast. But actively consider "could this be caused by something outside the code the user pointed at?" before settling on a code-level cause. Concretely: check whether secrets/config are correct in their actual store (not just assumed), whether migrations are actually applied in the affected environment, and whether the deployed artifact matches what you're reading, before concluding "the code is wrong."

If the relevant backend is Supabase/Azure/GitHub (Pioneer's default stack), read `references/supabase-azure-github.md` now for the specific things to check (RLS policies, migration state, edge function logs, secrets, Azure resource config) and use the Supabase MCP tools to check real state rather than guessing from the schema files.

**Research how this is supposed to work before deciding how it's broken.** If the bug involves a pattern with an established correct approach — auth flows, RLS policies, MCP tool auth, webhook verification, retry/idempotency, migration ordering — briefly check the actual current documentation or spec for that pattern (via context7, the Supabase docs tool, or a targeted web search) rather than relying purely on memory or intuition. Compare the present implementation against that standard. This is what turns "I think this looks wrong" into "this deviates from the documented behavior in this specific way."

**Output of this phase (internal, not yet shown to the user):** a root cause you have evidence for, and — importantly — an explicit note on what you checked and ruled out. If you're not confident in the root cause, say so rather than forcing a conclusion; it's fine for the plan phase to include "confirm X" as a first step.

## Phase 2 — Plan

Goal: a fix that addresses the actual root cause, at the layer where it actually lives, following the pattern that's standard for that situation — not the smallest diff that makes the symptom go away.

Draft a fix plan:
- What changes, and where (files, config, migration, secret, resource)
- Why this addresses the root cause specifically (tie it back to the evidence from Phase 1)
- How it aligns with the standard approach for this kind of problem (reference what you found in the research step, if applicable)
- How you'll verify it worked (see Verification below)

Keep the plan as small as the root cause allows. If the honest fix is a one-line change, don't pad it with unrelated cleanup; if the honest fix requires a migration plus a code change plus a secret rotation, say so plainly rather than under-scoping it to look simpler.

## Phase 3 — Adversarial review (do this yourself, silently, before showing anything)

Before presenting anything, argue against your own plan:

- **Does this actually fix the root cause, or just the symptom?** If someone reverted just the code change, would the bug come back because the real issue (bad data, wrong secret, unapplied migration) is still there?
- **Does fixing this introduce or expose a second failure?** E.g., fixing a query might reveal that the RLS policy still blocks it; fixing a client bug might reveal the API was never returning the right shape to begin with. Trace one layer further than the immediate fix to check.
- **Is there a simpler explanation you're overlooking?** Re-check the "is this even a code bug" question from Phase 1 one more time now that you have a specific plan — sunk cost in a theory is a common way analyses go wrong.
- **What would make this plan wrong?** If you can name a concrete way it could fail, either resolve it now or fold it into the plan as a step to confirm first.

If this review changes the plan, that's the process working, not a wasted step — revise and move on. Don't show your internal back-and-forth to the user; only the concluded result matters to them.

## Phase 4 — Report and get approval

Report plainly and concisely, before making any changes:

```
Root cause: <one or two sentences, plain language, no hedging padding>
Evidence: <what you actually checked that supports this — logs, query results, docs comparison, etc.>
Plan:
1. ...
2. ...
Verification: <how you'll confirm the fix worked>
```

Skip preamble and skip re-explaining the symptom back to the user — they already know what's broken. If there's real uncertainty left (e.g. two plausible root causes), say so and propose how you'd disambiguate, rather than picking one silently.

Then stop and wait for explicit approval before changing anything. Do not start executing while waiting, and do not treat "looks reasonable" framing in your own head as approval.

## Phase 5 — Execute and verify

Once approved, carry out the plan end-to-end. If execution surfaces something that contradicts the approved plan (e.g. the migration doesn't apply cleanly, or a check reveals a second root cause) — pause and report that before continuing, since you'd now be acting outside what was approved.

**Verification is part of the fix, not optional polish.** Use whatever is appropriate and already fits the codebase's own standards — this is usually one or more of:
- Running the existing automated test suite / the specific failing test
- Adding or updating a test that covers the bug, if the codebase has test coverage for adjacent code
- Re-running the reproduction from Phase 1 (the failing query, the failing request, the failing script) and confirming it now succeeds
- Checking logs/DB state directly (e.g. via the Supabase MCP) to confirm the underlying condition is actually fixed, not just that the code compiles
- Advisors/lint checks relevant to the change (e.g. Supabase security/performance advisors after a schema or RLS change)

Browser-based visual verification is explicitly out of scope for this skill — if the fix needs a human to look at rendered UI, say so and hand that back to the user instead of attempting it.

Close with a short summary: what changed, and what verification showed. No re-statement of the whole plan.

## Guardrails

- Never edit code as the first action on a bug report. Diagnosis comes first, always.
- Don't assume the bug is in the code the user named just because that's where the symptom appears.
- Don't propose a fix you haven't checked against how that kind of problem is standardly solved, when a standard clearly applies.
- Don't let "the fix is more work than I'd like" shrink the plan to something that doesn't actually address the root cause.
- If you reach Phase 2 and realize you don't actually have a confident root cause, say so in the report rather than presenting a guess as a conclusion — propose a diagnostic first step instead.
