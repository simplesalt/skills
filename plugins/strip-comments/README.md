# strip-comments

A Claude Code hook that keeps code free of commentary. Code should contain only
executable instructions; explanations belong in READMEs and in prompts written
for agents.

Before every Bash command that contains `git commit`, it:

- **Strips comments from the lines being committed.** Only added lines, in any
  language [Pygments](https://pygments.org) can lex, including shell inside
  YAML `run:` blocks and heredocs. It rewrites the staged copy only: the
  working tree keeps its comments, so `git status` shows a diff afterwards. A
  file is left alone if stripping would make it fail to parse, and a line
  containing `strip-comments:keep` is never touched. Shebangs stay.
- **Keeps untagged markdown out of the commit.** A `.md` file is committed only
  if it is a `README.md` or has a line `<!-- agent-prompt -->` near the top,
  after any frontmatter. Other markdown files are unstaged and stay in the
  working tree.
- **Tells the agent what it did**, as the hook's reason: which files lost how
  many comment lines, and which markdown files were left out and how to tag
  them.

It never blocks a commit. If it fails, the commit goes ahead with its comments.

## Install

```
/plugin marketplace add simplesalt/skills
/plugin install strip-comments@simplesalt
```

Needs `python3` and `git` on the PATH, and Pygments (`pip install pygments`).
Without Pygments the hook errors and commits go ahead with their comments.

Add the rule to the project's `CLAUDE.md` too, so the agent writes code that
way in the first place:

```
- Code must contain only executable instructions; never explain it. Comments are stripped on commit.
```

## Run it by hand

```
python3 scripts/strip-comments-precommit.py --report   # print a patch of what would change
python3 scripts/strip-comments-precommit.py --full     # strip every tracked file in the working tree
```

## License

[PolyForm Noncommercial 1.0.0](LICENSE).
