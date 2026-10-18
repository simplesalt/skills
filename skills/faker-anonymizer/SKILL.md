---
name: faker-anonymizer
description: Build a script that copies a relational SQL database into a descoped analytics copy with the same schema, replacing PII with Faker values that stay consistent for analytics, without ever reading the data. Use when someone wants an anonymized, masked or fake copy of a PostgreSQL, MySQL or SQLite database for analysts, testing, demos or AI agents.
license: PolyForm-Noncommercial-1.0.0 (see LICENSE)
compatibility: Python 3.10+ with Faker, or Node 22.5+ with @faker-js/faker. SQLite works out of the box; PostgreSQL and MySQL need their standard driver.
metadata:
  version: "0.3.0"
---

<!-- agent-prompt -->

# Faker anonymizer

You'll help the user produce a script that copies their database into a new one
with **the same schema**, where:

- every PII field is regenerated with Faker;
- fields they analyze are regenerated **deterministically**: the same injected
  seed and the same real record always produce the same fake record, so counts,
  joins and repeat behavior still work;
- every other PII field is generated **fresh** on each run;
- lookup fields point at the same output record they pointed at before;
- unstructured fields (notes, comments, descriptions) are emptied;
- tables analysts don't need (logins, sessions, settings, app metadata) are
  copied as empty tables.

Example: with seed A, "Joan Baez, 123 Main Street, Cheyenne, Wyoming" becomes
"Shelia Waller, 89567 Jennifer Valley, Port Sarah, Ohio" on every run. With seed
B she becomes "Karen Lewis, 12534 Jack Cliff, Cainland, South Carolina", again
on every run. Her phone number is different every run, because nobody analyzes
it.

**What this is for.** The output is a descoped data source for analytics. It is
not a database the original application can run on, and it isn't meant to be:
logins, settings and other plumbing are gone, and kept keys may point at tables
that are now empty. Say this to the user early.

**Scope: relational SQL databases only** (PostgreSQL, MySQL/MariaDB, SQLite).
Not key-value stores, document databases, graph databases, Hadoop/Hive, or
files. If the user's data lives in one of those, say this skill doesn't fit.

**Never look at the data itself.** Work from table names, column names and
declared types only. Don't run `SELECT *`, don't open exports, don't ask for
sample rows. If the user pastes rows anyway, don't copy any value into code,
config, tests, commits or replies.

## Step 1: Read the schema and make your guesses

Get the schema: DDL, ORM models, a `\d` / `.schema` / `DESCRIBE` dump, or a list
of tables, columns and types. Make sure you have **every table** in the
database, not only the interesting ones.

Then guess what each column holds from its name and type, using
`references/pii-field-names.md`. For every table, sort its columns into:

- **PII**, with the PII type you think it is (`full_name` → `name`,
  `cust_email` → `email`, `zip` → `zip`, `dob` → `date_of_birth`).
- **Unstructured** (notes, comments, description, message, body, any long text
  or JSON blob). These get dropped.
- **Keys and lookups**: primary keys, and every column that points at another
  table, by foreign key or by naming (`customer_id`, `owner_email`).
- **Everything else**: what you think passes through unchanged.

Also flag:

- **Whole tables to drop**: logins, sessions, credentials, tokens, audit logs,
  settings, migrations, version tables, small lookup and strings tables. When in
  doubt, drop it.
- **Text columns whose names suggest structured values**: a `birth_date`,
  `zip` or `amount` declared as `TEXT` or `VARCHAR` can hold any format, or
  junk. See step 3.

## Step 2: Ask the user to verify

Show your guesses table by table and say plainly that they're guesses: "This is
what I think each field is. Can you check it?" Then ask, in the same message:

1. Is each guess right? (A `name` column might hold company names; `contact`
   might be an email or a phone.)
2. Did I miss PII? Are there fields that hold it **without the name saying so**
   (`ref`, `extra`, `data`, `attr1`, `metadata`, `legacy_code` holding an SSN,
   a `title` holding a person's name)?
3. Which PII fields will you **analyze**, or need to stay consistent from run
   to run (counting unique customers, joining to other data, tracking a person
   over time)? The rest will be fresh fakes every run.
4. Which columns, taken together, identify one real record? (For a person,
   often name + email, or a customer number.) These seed the deterministic
   fakes.
5. Are the tables I'd drop OK to drop? Is there one you need that I marked?

Tell the user, in plain words, before they answer:

- **Fields that aren't redacted can still be sensitive.** Anything kept as is
  (amounts, timestamps, status codes, IDs) passes through unchanged, and real
  data often has PII in surprising places: an email in a "reference" field, a
  name in an address line, a phone number in a product code.
- **If the data is big or messy, run a PII scanner** (for example Microsoft
  Presidio) over the kept fields before relying on the script, and expect to
  need more than one pass of cleansing.
- **Faking a field destroys analysis of its value.** A fake state or birth date
  is random, so "customers by state" or "by age" will be meaningless. If they
  need that, keep a coarse version on purpose (state only, or birth year with
  `keep_year`) and accept the re-identification risk, or ask a privacy owner.

## Step 3: Standardize the source first, if needed

The script replaces values; it doesn't clean them. Tell the user that some
source data has to be standardized **before** this step, in their own
pipeline, and that this is a prerequisite, not something the script will fix:

- **Dates stored as text** in mixed formats (`NN/NN/NNNN`, `10-3-38`,
  `Wednesday, October 3rd, 1938`). If they want to keep part of a date, such as
  the birth year for age analysis but not the month and day, the column must
  first be ISO dates (`1938-10-03`) or split into separate year, month and day
  columns. `keep_year` stops the run on any value that isn't ISO.
- **Other structured values in text columns**: ZIP codes with and without
  `+4`, amounts with currency signs, phone numbers in many formats. If the
  field is faked, format doesn't matter. If it's kept, its mess, and whatever
  personal data hides in it, passes straight through.

## Step 4: Write `anonymize.config.json`

Start from `assets/anonymize.config.example.json`. Per table:

```json
"customers": {
  "entity": "person",
  "identity": ["full_name", "email"],
  "fields": {
    "full_name":  {"pii": "name",  "analytics": true},
    "email":      {"pii": "email", "analytics": true},
    "phone":      {"pii": "phone", "analytics": false},
    "birth_date": {"pii": "date_of_birth", "analytics": true, "keep_year": true}
  },
  "lookups": {},
  "keep": ["customer_id", "plan", "signup_date"],
  "drop": ["notes"]
}
```

and at the top level, `"drop_tables": ["user_logins", "app_settings"]`.

- `identity`: the columns from question 4. Required if any field has
  `"analytics": true`.
- `entity` (optional, defaults to the table name): tables that describe the
  same kind of record with the same identity columns share an entity, so the
  same person gets the same fake in both.
- `fields`: every confirmed PII column with its type and analytics flag.
  `keep_year` (dates only) keeps the real year and fakes the month and day.
- `lookups`: columns that point at another anonymized table. `references` is
  `"table.column"`. The output gets whatever new value that parent record got,
  so if `customers.email` is faked, `newsletter.email` follows it. `copy` fills
  denormalized columns from the parent's new values
  (`"ship_name": "full_name"`).
- `keep`: columns copied unchanged. Keys that aren't PII (auto-increment IDs)
  usually go here.
- `drop`: unstructured columns. They stay in the schema but every value is
  NULL. Set `"drop_value": ""` on the table if a dropped column is NOT NULL.
- `drop_tables`: tables copied with their schema and no rows. A column in a
  kept table that points at a dropped table should be dropped too; a lookup
  into one is refused.

**Every table goes in `tables` or `drop_tables`, and every column of a kept
table in exactly one place.** The script refuses to run otherwise, so a table
or column added later can't leak by default.

PII types:

| Type | Notes |
|---|---|
| `name`, `first_name`, `last_name` | One fake person per record; all three agree |
| `email`, `username`, `phone` | Built from the fake person's name; emails use `example.com/.net/.org` |
| `street_address`, `city`, `state`, `state_abbr`, `zip`, `country`, `address` | One fake US address per record; the ZIP is in the state |
| `date_of_birth` | 1936 to 2007; `keep_year` keeps the real year |
| `ssn`, `company`, `job`, `ip`, `credit_card`, `iban`, `url` | |
| Any Faker method | Python: method name (`license_plate`). JS: `module.method` (`vehicle.vin`) |

## Step 5: Show the plan for every table, before the script

Before you hand over any script, show the user exactly what will happen to
**every table in the database**. Generate it from the config; it reads no data
and needs no dependencies:

```bash
python templates/python/anonymize.py --config anonymize.config.json --plan
# or
node templates/javascript/anonymize.mjs --config anonymize.config.json --plan
```

For each table it lists:

- **Passes through unredacted**: copied exactly as in the source.
- **Random on every run**: new fakes each run, unrelated between runs.
- **Same output for the same seed; relations kept**: deterministic fakes, plus
  lookups that still point at the same record and columns copied from it.
- **Dropped (emptied)**: in the schema, but every value is NULL.

and ends with the tables dropped whole. Check that every table from step 1
appears, either with its columns or under dropped tables. Show the plan to the
user and ask them to confirm it, or say what to move. Update the config and
show the plan again until they agree. Point at the "Passes through unredacted"
lines in particular: those values leave untouched.

## Step 6: Install the script

Use the user's default environment: Python if the project is Python (or
there's no strong signal), JavaScript if it's Node. Pick the standard driver
for their database:

| Database | Python | JavaScript |
|---|---|---|
| SQLite | `sqlite3` (built in) | `node:sqlite` (built in, Node 22.5+) |
| PostgreSQL | `psycopg` | `pg` |
| MySQL / MariaDB | `PyMySQL` | `mysql2` |

Copy `templates/python/` or `templates/javascript/` into the user's repo (for
example `tools/anonymize/`) with the agreed config. **Don't rewrite the
seeding, lookup or persona code**: it's the part that's easy to get subtly
wrong. Change the template only for things the config can't express, keep the
seeding rules intact if you do, and run `--plan` again afterwards.

## Step 7: Explain the seed, then hand off the run

The injected seed (`ANON_SEED`) is **functionally a secret**. Say this to the
user explicitly: anyone who has the anonymized copy *and* the seed can take a
list of candidate real people, run the script's seeding on them, and match the
fakes back to the originals. Keep it in a secret manager or CI secret, never in
the repo, the config, logs or the output. Rotate it if it leaks, and when you
don't need runs to line up with each other. Keep it the same when analysts
compare releases.

Give the user the commands to run where the data is. They run it, not you:

```bash
export ANON_SEED="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"   # or from the secret store
python anonymize.py --config anonymize.config.json \
    --source sqlite:///prod.db --target sqlite:///anonymized.db --verify
# or
node anonymize.mjs --config anonymize.config.json \
    --source postgresql://.../prod --target postgresql://.../anon --verify
```

For SQLite the script copies the schema itself. For PostgreSQL or MySQL the
target must already have the same schema, with no rows:
`pg_dump --schema-only prod | psql anon` or `mysqldump --no-data prod | mysql anon`.
If a kept table has a foreign key into a dropped table, remove that constraint
in the target or drop the column (it would be NULL anyway).

## Step 8: Read the report

The script prints counts only, never values, so you can read it.

- `fresh_identity_fallback`: rows whose identity columns were all empty. They
  got fresh fakes, so they won't be consistent between runs.
- `orphan_lookups`: lookup values with no matching parent. They were set to
  NULL. Ask the user whether that's expected.
- `verify.same_columns` / row counts: must match.
- `verify.pii_values_unchanged`: how many PII values came out equal to the
  original. A few matches on `state` or `city` are chance. A count near the row
  total means the field isn't being replaced; check the config.
- `verify.lookups_not_found`: must be empty.

Then remind the user of step 2: kept fields weren't scanned, so for big or
messy data, run a PII scanner over the output and fix the config until it's
clean.

## Gotchas

- Pin the Faker version (`requirements.txt` / `package.json` do). A different
  version can turn the same seed into different fakes.
- Python and JavaScript produce different fakes from the same seed. Pick one
  per pipeline.
- If a person's identity values change (new email), they become a different
  fake person. Choose identity columns that don't change, or a stable customer
  number.
- Deterministic fakes keep the shape of the data: how many records share a
  value, how often a person appears. In small data sets, that alone can point
  at someone.
- Lookups are held in memory. For tables with tens of millions of rows,
  switch the lookup map to a temporary table.
