# simplesalt skills

[Agent Skills](https://agentskills.io) for coding agents. Each folder under
`skills/` is one skill: copy it where your agent loads skills (for Claude
Code, `.claude/skills/` in a repo or `~/.claude/skills/`).

| Skill | What it does |
|---|---|
| [faker-anonymizer](skills/faker-anonymizer/) | Has the agent build a script that copies a relational SQL database into an anonymized analytics copy with the same schema, replacing PII with Faker values that stay consistent for analysis, without ever reading the data. |

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md). Free for noncommercial use. If you
pass on any part of these skills, including inside another project, keep the
license and its `Required Notice` line with it. For commercial use, contact
simplesalt.
