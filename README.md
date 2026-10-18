# Simple Salt skills

[Agent Skills](https://agentskills.io) and a Claude Code hook for coding
agents.

With Claude Code, add the marketplace and install what you want:

```
/plugin marketplace add simplesalt/skills
/plugin install simplesalt-skills@simplesalt
/plugin install strip-comments@simplesalt
```

Or copy a folder from `skills/` to wherever your agent loads skills (for Claude
Code, `.claude/skills/` in a repo or `~/.claude/skills/`), with its `LICENSE`.

| Skill | What it does |
|---|---|
| [faker-anonymizer](skills/faker-anonymizer/) | Has the agent build a script that copies a relational SQL database into an anonymized analytics copy with the same schema, replacing PII with Faker values that stay consistent for analysis, without ever reading the data. |
| [clarify](skills/clarify/) | Turns a vague idea into a clear one through a Socratic dialogue: the agent asks questions, reflects back, and keeps a record of what's settled and what's still open. |

## Hooks

| Plugin | What it does |
|---|---|
| [strip-comments](plugins/strip-comments/) | Before each `git commit`, strips comments from the staged lines and keeps untagged markdown out of the commit, then tells the agent what it did. |

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Free for noncommercial use. If you
pass on any part of this repo, including inside another project, keep the
license and its `Required Notice` line with it. For commercial use, contact
Simple Salt.
