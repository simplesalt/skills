#!/usr/bin/env node
import { createHmac, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";

const BATCH = 1000;

const canonical = (values) => values.map((v) => (v === null || v === undefined ? "" : String(v).trim())).join("\x1f");

const recordKey = (seed, entity, identity) =>
  createHmac("sha256", seed).update(`${entity}\x1e${canonical(identity)}`).digest();

const groupSeed = (key, group) => {
  const d = createHmac("sha256", key).update(group).digest();
  return [d.readUInt32BE(0), d.readUInt32BE(4), d.readUInt32BE(8), d.readUInt32BE(12)];
};

const GROUPS = {
  person: ["first_name", "last_name", "name"],
  contact: ["email", "username", "phone"],
  address: ["street_address", "city", "state", "state_abbr", "zip", "country", "address"],
};

const SINGLES = {
  date_of_birth: (f) => f.date.birthdate({ mode: "year", min: 1936, max: 2007 }).toISOString().slice(0, 10),
  ssn: (f) => f.helpers.replaceSymbols("###-##-####"),
  company: (f) => f.company.name(),
  job: (f) => f.person.jobTitle(),
  ip: (f) => f.internet.ipv4(),
  credit_card: (f) => f.finance.creditCardNumber(),
  iban: (f) => f.finance.iban(),
  url: (f) => f.internet.url(),
};

class Persona {
  constructor(faker, key) {
    this.f = faker;
    this.key = key;
    this.cache = {};
  }

  group(name) {
    if (!(name in this.cache)) {
      this.f.seed(groupSeed(this.key, name));
      this.cache[name] = this[name]();
    }
    return this.cache[name];
  }

  person() {
    const first = this.f.person.firstName();
    const last = this.f.person.lastName();
    return { first_name: first, last_name: last, name: `${first} ${last}` };
  }

  contact() {
    const p = this.group("person");
    const tag = this.key.toString("hex").slice(0, 4);
    const user = `${p.first_name}.${p.last_name}`.toLowerCase().replace(/[\s']/g, "");
    return {
      email: `${user}${tag}@${this.f.helpers.arrayElement(["example.com", "example.net", "example.org"])}`,
      username: `${user}${tag}`,
      phone: this.f.phone.number(),
    };
  }

  address() {
    const abbrs = this.f.definitions.location.state_abbr;
    const i = this.f.number.int({ min: 0, max: abbrs.length - 1 });
    const state_abbr = abbrs[i];
    const state = this.f.definitions.location.state[i];
    const street_address = this.f.location.streetAddress();
    const city = this.f.location.city();
    const zip = this.f.location.zipCode({ state: state_abbr });
    return { street_address, city, state, state_abbr, zip, country: "United States",
             address: `${street_address}, ${city}, ${state_abbr} ${zip}` };
  }

  get(pii) {
    for (const [group, attrs] of Object.entries(GROUPS)) {
      if (attrs.includes(pii)) return this.group(group)[pii];
    }
    if (!(pii in this.cache)) {
      let make = SINGLES[pii];
      if (!make) {
        const [mod, fn] = pii.split(".");
        if (typeof this.f[mod]?.[fn] !== "function") throw new Error(`unknown pii type ${JSON.stringify(pii)}`);
        make = (f) => f[mod][fn]();
      }
      this.f.seed(groupSeed(this.key, pii));
      this.cache[pii] = make(this.f);
    }
    return this.cache[pii];
  }
}

function keepYear(table, col, original, fake) {
  const text = original instanceof Date ? original.toISOString() : String(original);
  if (!/^\d{4}-\d{2}-\d{2}/.test(text)) {
    throw new Error(`${table}.${col} has a value that isn't an ISO date (YYYY-MM-DD); standardize the source before anonymizing`);
  }
  const year = Number(text.slice(0, 4));
  let monthDay = fake.slice(5, 10);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  if (monthDay === "02-29" && !leap) monthDay = "02-28";
  return `${year}-${monthDay}`;
}

async function connect(url) {
  const scheme = url.split(":")[0];
  const kind = scheme.split("+")[0];
  if (kind === "sqlite") {
    const { DatabaseSync } = await import("node:sqlite");
    const path = url.replace(/^sqlite:\/\//, "").replace(/^\/(?!\/)/, "") || ":memory:";
    const db = new DatabaseSync(path.startsWith("//") ? path.slice(1) : path);
    return {
      kind, q: '"',
      async query(sql, params = []) {
        const stmt = db.prepare(sql);
        return /^\s*(select|pragma)/i.test(sql) ? stmt.all(...params) : (stmt.run(...params), []);
      },
      async tables() {
        return db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
          .all().map((r) => r.name).sort();
      },
      async columns(table) {
        return db.prepare(`PRAGMA table_info("${table}")`).all().map((c) => c.name);
      },
      async begin() { db.exec("BEGIN"); },
      async commit() { db.exec("COMMIT"); },
      raw: db,
      ph: () => "?",
      close() { db.close(); },
    };
  }
  if (kind === "postgres" || kind === "postgresql") {
    const { default: pg } = await import("pg");
    const client = new pg.Client({ connectionString: url });
    await client.connect();
    return {
      kind, q: '"',
      async query(sql, params = []) { return (await client.query(sql, params)).rows; },
      async tables() {
        const r = await client.query("SELECT table_name FROM information_schema.tables " +
          "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'");
        return r.rows.map((x) => x.table_name).sort();
      },
      async columns(table) {
        const r = await client.query(`SELECT * FROM "${table}" WHERE 1 = 0`);
        return r.fields.map((f) => f.name);
      },
      async begin() { await client.query("BEGIN"); },
      async commit() { await client.query("COMMIT"); },
      ph: (i) => `$${i + 1}`,
      close() { return client.end(); },
    };
  }
  if (kind === "mysql") {
    const mysql = await import("mysql2/promise");
    const conn = await mysql.createConnection(url);
    return {
      kind, q: "`",
      async query(sql, params = []) { return (await conn.query(sql, params))[0]; },
      async tables() {
        const [rows] = await conn.query("SELECT table_name AS name FROM information_schema.tables " +
          "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'");
        return rows.map((x) => x.name).sort();
      },
      async columns(table) {
        const [, fields] = await conn.query(`SELECT * FROM \`${table}\` WHERE 1 = 0`);
        return fields.map((f) => f.name);
      },
      async begin() { await conn.beginTransaction(); },
      async commit() { await conn.commit(); },
      ph: () => "?",
      close() { return conn.end(); },
    };
  }
  throw new Error(`unsupported database URL scheme ${scheme}`);
}

const ident = (db, name) => `${db.q}${name}${db.q}`;

async function* readRows(db, table, cols, orderBy) {
  const order = orderBy ? ` ORDER BY ${ident(db, orderBy)}` : "";
  for (let offset = 0; ; offset += BATCH) {
    const rows = await db.query(
      `SELECT ${cols.map((c) => ident(db, c)).join(", ")} FROM ${ident(db, table)}${order} LIMIT ${BATCH} OFFSET ${offset}`);
    if (!rows.length) return;
    for (const r of rows) yield cols.map((c) => r[c]);
  }
}

async function insertRows(db, table, cols, rows) {
  for (const row of rows) {
    await db.query(
      `INSERT INTO ${ident(db, table)} (${cols.map((c) => ident(db, c)).join(", ")}) VALUES (${cols.map((_, i) => db.ph(i)).join(", ")})`,
      row);
  }
}

async function count(db, table) {
  const r = await db.query(`SELECT COUNT(*) AS n FROM ${ident(db, table)}`);
  return Number(r[0].n);
}

async function copySqliteSchema(src, dst) {
  const rows = await src.query(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END");
  for (const { sql } of rows) dst.raw.exec(sql);
}

function loadConfig(path) {
  const config = JSON.parse(readFileSync(path, "utf8"));
  config.drop_tables ??= [];
  for (const [table, spec] of Object.entries(config.tables)) {
    spec.identity ??= [];
    spec.fields ??= {};
    spec.lookups ??= {};
    spec.keep ??= [];
    spec.drop ??= [];
    if (Object.values(spec.fields).some((f) => f.analytics) && !spec.identity.length) {
      throw new Error(`${table} has analytics fields but no identity columns`);
    }
    for (const [col, lk] of Object.entries(spec.lookups)) {
      const parent = lk.references.split(".")[0];
      if (!(parent in config.tables)) {
        throw new Error(`${table}.${col} points at ${parent}, which isn't anonymized; drop ${table}.${col} too, or anonymize ${parent}`);
      }
    }
  }
  return config;
}

function plan(config) {
  const lines = ["# Anonymization plan", "",
    "The output is a descoped copy for analytics, not a working copy of the application.", ""];
  for (const [table, spec] of Object.entries(config.tables)) {
    const fields = Object.entries(spec.fields);
    const unredacted = [...spec.keep];
    const random = fields.filter(([, f]) => !f.analytics).map(([c, f]) => `${c} (${f.pii})`);
    const seeded = fields.filter(([, f]) => f.analytics)
      .map(([c, f]) => `${c} (${f.pii}${f.keep_year ? ", real year kept" : ""})`);
    for (const [col, lk] of Object.entries(spec.lookups)) {
      seeded.push(`${col} (points at ${lk.references})`);
      for (const [c, p] of Object.entries(lk.copy ?? {})) seeded.push(`${c} (copied from ${lk.references.split(".")[0]}.${p})`);
    }
    lines.push(`## ${table}`, "");
    if (spec.identity.length) lines.push(`Records are identified by: ${spec.identity.join(", ")}`, "");
    for (const [title, cols] of [["Passes through unredacted", unredacted], ["Random on every run", random],
                                 ["Same output for the same seed; relations kept", seeded], ["Dropped (emptied)", spec.drop]]) {
      lines.push(`- **${title}:** ${cols.length ? cols.join(", ") : "none"}`);
    }
    lines.push("");
  }
  lines.push("## Dropped tables (schema only, no rows)", "", config.drop_tables.length ? config.drop_tables.join(", ") : "none", "");
  return lines.join("\n");
}

function tableOrder(config) {
  const order = [];
  const seen = new Set();
  const visit = (t, path = []) => {
    if (seen.has(t)) return;
    if (path.includes(t)) throw new Error(`lookup cycle through ${t}`);
    for (const lk of Object.values(config.tables[t].lookups)) {
      const parent = lk.references.split(".")[0];
      if (parent !== t) visit(parent, [...path, t]);
    }
    seen.add(t);
    order.push(t);
  };
  Object.keys(config.tables).forEach((t) => visit(t));
  return order;
}

async function checkCoverage(config, src) {
  const errors = [];
  const known = new Set([...Object.keys(config.tables), ...config.drop_tables]);
  const present = await src.tables();
  present.filter((t) => !known.has(t))
    .forEach((t) => errors.push(`table ${t}: not in config (add it to tables or drop_tables; when in doubt, drop it)`));
  [...known].sort().filter((t) => !present.includes(t)).forEach((t) => errors.push(`table ${t}: in config but not in the database`));
  if (errors.length) throw new Error(`config doesn't cover the schema:\n  ${errors.join("\n  ")}`);
  for (const [table, spec] of Object.entries(config.tables)) {
    const cols = await src.columns(table);
    const listed = new Set([...Object.keys(spec.fields), ...Object.keys(spec.lookups), ...spec.keep, ...spec.drop]);
    for (const lk of Object.values(spec.lookups)) Object.keys(lk.copy ?? {}).forEach((c) => listed.add(c));
    cols.filter((c) => !listed.has(c)).forEach((c) => errors.push(`${table}.${c}: not in config (add it to fields, lookups, keep or drop)`));
    [...listed].filter((c) => !cols.includes(c)).forEach((c) => errors.push(`${table}.${c}: in config but not in the table`));
  }
  if (errors.length) throw new Error(`config doesn't cover the schema:\n  ${errors.join("\n  ")}`);
}

async function anonymize(config, src, dst, seed) {
  const { fakerEN_US: faker } = await import("@faker-js/faker");
  const referenced = new Map();
  for (const spec of Object.values(config.tables)) {
    for (const lk of Object.values(spec.lookups)) if (!referenced.has(lk.references)) referenced.set(lk.references, new Map());
  }
  const report = {};
  for (const table of tableOrder(config)) {
    const spec = config.tables[table];
    const cols = await src.columns(table);
    const idx = Object.fromEntries(cols.map((c, i) => [c, i]));
    const stats = { rows: 0, fresh_identity_fallback: 0, orphan_lookups: 0 };
    let batch = [];
    await dst.begin();
    for await (const row of readRows(src, table, cols, spec.page_by)) {
      const out = [...row];
      const identity = spec.identity.map((c) => row[idx[c]]);
      let det;
      if (spec.identity.length && identity.every((v) => v === null || v === "")) {
        det = new Persona(faker, randomBytes(32));
        stats.fresh_identity_fallback++;
      } else {
        det = new Persona(faker, recordKey(seed, spec.entity ?? table, identity));
      }
      const fresh = new Persona(faker, randomBytes(32));
      for (const [col, field] of Object.entries(spec.fields)) {
        if (row[idx[col]] === null) continue;
        const value = (field.analytics ? det : fresh).get(field.pii);
        out[idx[col]] = field.keep_year ? keepYear(table, col, row[idx[col]], value) : value;
      }
      for (const col of spec.drop) out[idx[col]] = spec.drop_value ?? null;
      for (const [col, lk] of Object.entries(spec.lookups)) {
        const old = row[idx[col]];
        if (old === null) continue;
        const parentRow = referenced.get(lk.references).get(String(old));
        if (!parentRow) {
          stats.orphan_lookups++;
          out[idx[col]] = null;
          Object.keys(lk.copy ?? {}).forEach((c) => { out[idx[c]] = null; });
          continue;
        }
        out[idx[col]] = parentRow[lk.references.split(".")[1]];
        for (const [c, parentCol] of Object.entries(lk.copy ?? {})) out[idx[c]] = parentRow[parentCol];
      }
      for (const [ref, mapping] of referenced) {
        const [t, c] = ref.split(".");
        if (t === table) mapping.set(String(row[idx[c]]), Object.fromEntries(cols.map((k, i) => [k, out[i]])));
      }
      batch.push(out);
      stats.rows++;
      if (batch.length >= BATCH) { await insertRows(dst, table, cols, batch); batch = []; }
    }
    if (batch.length) await insertRows(dst, table, cols, batch);
    await dst.commit();
    report[table] = stats;
  }
  return report;
}

async function verify(config, src, dst) {
  const result = {};
  let ok = true;
  for (const [table, spec] of Object.entries(config.tables)) {
    const cols = await src.columns(table);
    const r = { same_columns: JSON.stringify(cols) === JSON.stringify(await dst.columns(table)),
                rows_source: await count(src, table), rows_target: await count(dst, table) };
    const idx = Object.fromEntries(cols.map((c, i) => [c, i]));
    const unchanged = Object.fromEntries(Object.keys(spec.fields).map((c) => [c, 0]));
    const a = readRows(src, table, cols, spec.page_by);
    const b = readRows(dst, table, cols, spec.page_by);
    for (;;) {
      const [x, y] = [await a.next(), await b.next()];
      if (x.done || y.done) break;
      for (const c of Object.keys(spec.fields)) {
        if (x.value[idx[c]] !== null && String(x.value[idx[c]]) === String(y.value[idx[c]])) unchanged[c]++;
      }
    }
    r.pii_values_unchanged = Object.fromEntries(Object.entries(unchanged).filter(([, n]) => n));
    r.lookups_not_found = {};
    for (const [col, lk] of Object.entries(spec.lookups)) {
      const [pt, pc] = lk.references.split(".");
      const parent = new Set();
      for await (const [v] of readRows(dst, pt, [pc])) parent.add(String(v));
      let n = 0;
      for await (const [v] of readRows(dst, table, [col])) if (v !== null && !parent.has(String(v))) n++;
      if (n) r.lookups_not_found[col] = n;
    }
    r.passed = r.same_columns && r.rows_source === r.rows_target && !Object.keys(r.lookups_not_found).length;
    ok &&= r.passed;
    result[table] = r;
  }
  return [ok, result];
}

async function main() {
  const { values: args } = parseArgs({ options: {
    config: { type: "string" }, source: { type: "string" }, target: { type: "string" },
    "seed-env": { type: "string", default: "ANON_SEED" }, verify: { type: "boolean", default: false },
    plan: { type: "boolean", default: false } } });
  if (!args.config) throw new Error("usage: --config FILE (--plan | --source URL --target URL [--verify])");
  if (args.plan) { console.log(plan(loadConfig(args.config))); return; }
  if (!args.source || !args.target) throw new Error("--source and --target are required unless --plan is given");
  const raw = process.env[args["seed-env"]] ?? "";
  if (raw.length < 32) throw new Error(`set ${args["seed-env"]} to a secret of at least 32 characters`);
  const config = loadConfig(args.config);
  const src = await connect(args.source);
  const dst = await connect(args.target);
  await checkCoverage(config, src);
  if (src.kind === "sqlite" && dst.kind === "sqlite") await copySqliteSchema(src, dst);
  for (const table of [...Object.keys(config.tables), ...config.drop_tables]) {
    if (JSON.stringify(await src.columns(table)) !== JSON.stringify(await dst.columns(table))) {
      throw new Error(`target table ${table} doesn't have the source's columns`);
    }
    if (await count(dst, table)) throw new Error(`target table ${table} isn't empty`);
  }
  const report = { anonymized: await anonymize(config, src, dst, Buffer.from(raw)) };
  let ok = true;
  if (args.verify) [ok, report.verify] = await verify(config, src, dst);
  console.log(JSON.stringify(report, null, 2));
  await src.close();
  await dst.close();
  process.exit(ok ? 0 : 1);
}

main().catch((e) => { console.error(`error: ${e.message}`); process.exit(1); });
