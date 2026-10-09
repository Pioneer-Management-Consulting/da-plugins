# haiku-max plugin

Applies Claude Haiku 5.5 best practices automatically. Covers Claude Code and Claude Desktop. API-only guidance is excluded.

## Skills
1. haiku-max: triggers when Haiku is the running model (main session, subagent, chat) or when a parent session delegates to a Haiku subagent. Gives core rules, verify-before-done, effort advice, escalation rules, and a delegation brief template.

## Limits
- Skill triggering is description-matched, not guaranteed. A subagent self-triggers only if it has the Skill tool. The "parent delegating" section is the mitigation: the parent pastes a rules block into the brief.
- Optional hardening: add this line to your CLAUDE.md. Plugins cannot ship CLAUDE.md.
  `Before delegating to a Haiku subagent, invoke the haiku-max skill.`
- No `version` field. Updates follow git commits.

## Structure
```
haiku-max
├── .claude-plugin/
│   └── plugin.json          # plugin manifest (no version)
└── skills/
    └── haiku-max/
        └── SKILL.md
```
