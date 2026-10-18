# faker-anonymizer

An [Agent Skill](https://agentskills.io) that has a coding agent build a script
to copy a relational SQL database (PostgreSQL, MySQL/MariaDB, SQLite) into an
anonymized one with **the same schema**, using
[Faker](https://github.com/joke2k/faker) ([JS](https://fakerjs.dev)). The
agent works from table and field names only and never looks at the data.

The result is a descoped data source for analytics, not a copy the original
application can run on. Key-value, document, graph and Hadoop stores are out
of scope.

## What you get

- **Every PII field regenerated.** Names, emails, phones, addresses, birth
  dates, IDs.
- **Consistent where you analyze.** For fields you mark as analytics, the
  record's identifying values are combined with an injected seed, hashed
  (HMAC-SHA256) and used to seed Faker. The same seed and the same record
  always give the same fake record, so counts, joins and repeat behavior work.
  Change the seed and everyone becomes someone else.
- **Fresh everywhere else.** Non-analytics PII is newly generated every run.
- **Lookups stay intact.** A column that points at another table points at the
  same output record. If the parent's email is faked, the child's email follows.
- **Comments and notes emptied.** Unstructured fields are dropped (set to NULL)
  because they hide PII that no field name reveals.
- **Plumbing tables emptied.** Logins, sessions, settings, migrations and
  other application tables go under `drop_tables`: schema kept, no rows. When
  in doubt, drop it.
- **Birth year, if you need it.** `keep_year` keeps the real year of a date and
  fakes the month and day. It needs ISO dates, so it stops on messy text dates
  rather than guessing.
- **Fails closed.** Every table must be anonymized or dropped, and every column
  listed as PII, lookup, keep or drop, so a new table or column can't slip
  through.

```
seed A:  Joan Baez, 123 Main Street, Cheyenne, Wyoming  ->  Shelia Waller, 89567 Jennifer Valley, Port Sarah, Ohio
seed B:  Joan Baez, 123 Main Street, Cheyenne, Wyoming  ->  Karen Lewis, 12534 Jack Cliff, Cainland, South Carolina
```

**The seed is a secret.** Anyone with the anonymized copy and the seed can
regenerate the fake for any real person they suspect is in it and match them
up.

## How the agent uses it

1. Reads the schema of every table and guesses what each column holds from its
   name: PII and its type, free text, keys and lookups, tables to drop whole,
   and text columns that look like they hold dates or numbers.
2. Asks you to verify those guesses, whether any other field holds PII without
   its name saying so, which fields you'll analyze, and which columns identify
   a record.
3. Tells you what to standardize first (for example, text birth dates in mixed
   formats need to become ISO dates before the year can be kept).
4. Writes `anonymize.config.json`.
5. Shows you a plan for every table, generated with `--plan` from the config:
   what passes through unredacted, what's random on every run, what stays the
   same for a given seed with relations kept, and what's dropped. You confirm
   it before any script is installed.
6. Copies the Python or JavaScript template, whichever matches your project.
7. Hands you the command to run where the data is, then reads the counts-only
   report.

Fields kept as-is aren't scanned. For big or messy data, run a PII scanner
such as [Presidio](https://github.com/microsoft/presidio) over them too, and
expect more than one cleansing pass.

## Layout

```
faker-anonymizer/
  SKILL.md                         the agent's instructions
  LICENSE.md                       PolyForm Noncommercial 1.0.0
  references/pii-field-names.md    name patterns that suggest PII
  assets/anonymize.config.example.json
  templates/python/                anonymize.py, requirements.txt (sqlite3, psycopg, PyMySQL)
  templates/javascript/            anonymize.mjs, package.json (node:sqlite, pg, mysql2)
  tests/                           synthetic fixture and property tests
```

Install the `faker-anonymizer/` folder where your agent loads skills (for
Claude Code, `.claude/skills/` in the repo or `~/.claude/skills/`). Keep
`LICENSE.md` with it.

## Test

```bash
pip install Faker==40.43.0
bash skills/faker-anonymizer/tests/run_tests.sh
```

The JavaScript template is tested too when npm is present. The tests build a 2,000-customer SQLite database and check both templates:
same seed gives identical analytics fakes, a different seed gives different
ones, non-analytics fields change every run, notes are empty, dropped tables
have no rows, the schema is identical, and orders and newsletter rows still
point at the right customer. They also check `keep_year`, that a messy text
date stops the run, that `--plan` covers every table, and that an unlisted
table or a lookup into a dropped table is refused.

## Status

0.3.0 strawman. US-style addresses only. Both templates tested on SQLite and
PostgreSQL 16 (same seed gave the same fakes on both); the MySQL path uses the
standard driver but hasn't been run against a server yet. The JavaScript
template inserts one row at a time, so it's slow on big tables.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md). Free for noncommercial use. If you
pass on any part of it, including inside another project, keep the license
and its `Required Notice` line with it. For commercial use, contact
simplesalt.
