---
name: test-checklist
description: Build an Excel test checklist for a feature. Asks about testers, access, environment, and the production scenario; reads the code to find the business rules and gates that matter; writes start-to-finish test procedures to docs/<feature>-test-checklist.xlsx.
disable-model-invocation: true
argument-hint: "[feature]"
---

# Test checklist

Make an Excel checklist that testers run from top to bottom. The purpose is to expose issues in **typical production use**. The order follows how real users will use the feature.

Feature: `$ARGUMENTS` (if empty, ask in Round 1).

## 1. Round 1 questions

Use AskUserQuestion. Skip any question the arguments or the conversation already answer.

- **Feature + source:** Which feature? Where is the code: branch, PR, commit range, or already-merged files/folders?
- **Production scenario:** How will real users use the feature, from start to finish?
- **Testers + access:** Who can test? Their roles, accounts, and sign-in methods.
- **Environment + cleanup:** Where do tests run? If production: use a test-data prefix (e.g. `ZZ UAT`) and add a cleanup section.

## 2. Investigate the code

- Find the feature's code. A diff can contain other features: test only the named feature. If the feature is already merged, find it with `git log -- <paths>`, grep, and the docs, not the diff.
- Make a **rules inventory**. List each gate and check with its `file:line`:
  - client validation and messages; role and route guards
  - API/server auth; DB constraints, unique indexes, triggers, access policies
  - state changes (draft/open/closed), scheduled jobs, notifications
  - date inputs: find the stored time and time zone for each one
- Keep a rule only if its failure would block the production scenario, break access or security, or lose or corrupt data. Leave out UI details that do not change the result.
- Note **defects**: bugs at any level (UI, API, database, access policies), and client and server checks that disagree.

## 3. Round 2 questions

Ask only what the code made relevant. Skip questions that earlier answers already cover.
- **Defects:** Show each defect from step 2. For each, ask: fix it now, or ignore it for now? Do not write tests that are expected to fail.
- Which modes or variants to cover.
- How to test time-based behavior: short time windows, database checks, or skip.
- Which tester plays each role. Include negative roles (wrong group, no account, not invited).
- Show the rules inventory in short form and ask: "Did I miss any rules?"

## 4. Write the test plan

- **Prerequisites:** Describe the state the tests start from (e.g. "Project created and approved. Two custom groups exist."). Do not write steps for work outside the feature, such as intake or approvals.
- **Section order** (drop sections that do not apply): Pre-flight → Access / sign-in → Setup → Configure → First use → Repeat use / time-based → Results → Close → Cleanup.
- Put each test in the first section where its prerequisites exist.
- Each kept rule gets a test that proves it **allows** the right user and a test that proves it **blocks** the wrong user, where that applies.
- Each item has three fields:
  - `test`: what we are testing (a few words)
  - `how`: steps. Start with the role (e.g. "Tester B:"). Use the real UI labels from the code. Separate steps with `\n`.
  - `criteria`: what you can see when the test passes. Use exact messages from the code.
- For secrets and keys: check names only. Never copy values.
- Keep every field brief. No prose.
- Gut check: if you listed 60 items, that is too long. Cut tests that do not expose issues in typical use.

## 5. Build the workbook

1. Write the plan as JSON to the scratchpad:
   ```json
   {
     "title": "Feature name: Test Checklist",
     "prerequisites": ["Project created and approved.", "Two custom groups exist."],
     "roles": [{"role": "Tester A", "account": "a@client.com", "access": "Google", "setup": "In Group 1"}],
     "sections": [{"name": "Access", "items": [
       {"test": "One submission per cycle", "how": "Tester A: open the link again.\nSubmit again.", "criteria": "'Already Submitted' shows. No second record."}
     ]}]
   }
   ```
2. Check `python -c "import openpyxl"` (use `python3` on macOS). If it fails, ask the user before you run `pip install openpyxl`.
3. Run: `python <skill-dir>/scripts/fill_checklist.py <json> <repo-root>/docs/<feature-slug>-test-checklist.xlsx`

The script puts Prerequisites first, numbers items (1.1, 1.2…), sets Status to "Not run" with a dropdown, and leaves Notes blank. To change the look, edit `template.xlsx` (sample rows 3–4 on Checklist, row 2 on Test roles), not the script.

## 6. Report

Give the user:
- the file path
- a table of sections with item counts
- the rules you left out, and why
- assumptions that are not in the Q&A
