#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sys
from urllib.parse import unquote, urlparse

BATCH = 1000


def canonical(values):
    return "\x1f".join("" if v is None else str(v).strip() for v in values)


def record_key(seed, entity, identity_values):
    return hmac.new(seed, f"{entity}\x1e{canonical(identity_values)}".encode(), hashlib.sha256).digest()


def group_seed(key, group):
    return int.from_bytes(hmac.new(key, group.encode(), hashlib.sha256).digest()[:8], "big")


class Persona:
    def __init__(self, faker, key):
        self.f, self.key, self.cache = faker, key, {}

    def _group(self, name):
        if name not in self.cache:
            self.f.seed_instance(group_seed(self.key, name))
            self.cache[name] = getattr(self, "_" + name)()
        return self.cache[name]

    def _person(self):
        first, last = self.f.first_name(), self.f.last_name()
        return {"first_name": first, "last_name": last, "name": f"{first} {last}"}

    def _contact(self):
        p = self._group("person")
        tag = self.key.hex()[:4]
        user = f"{p['first_name']}.{p['last_name']}".lower().replace(" ", "").replace("'", "")
        return {
            "email": f"{user}{tag}@{self.f.random_element(['example.com', 'example.net', 'example.org'])}",
            "username": f"{user}{tag}",
            "phone": self.f.phone_number(),
        }

    def _address(self):
        state_abbr = self.f.state_abbr(include_territories=False)
        street = self.f.street_address()
        city = self.f.city()
        zipcode = self.f.zipcode_in_state(state_abbr)
        state = STATE_NAMES.get(state_abbr, state_abbr)
        return {"street_address": street, "city": city, "state": state, "state_abbr": state_abbr,
                "zip": zipcode, "country": "United States",
                "address": f"{street}, {city}, {state_abbr} {zipcode}"}

    def get(self, pii):
        for group, attrs in GROUPS.items():
            if pii in attrs:
                return self._group(group)[pii]
        if pii in SINGLES:
            return self._single(pii, SINGLES[pii])
        if hasattr(self.f, pii):
            return self._single(pii, lambda f: getattr(f, pii)())
        raise SystemExit(f"error: unknown pii type {pii!r}")

    def _single(self, pii, make):
        if pii not in self.cache:
            self.f.seed_instance(group_seed(self.key, pii))
            self.cache[pii] = make(self.f)
        return self.cache[pii]


GROUPS = {
    "person": {"first_name", "last_name", "name"},
    "contact": {"email", "username", "phone"},
    "address": {"street_address", "city", "state", "state_abbr", "zip", "country", "address"},
}
SINGLES = {
    "date_of_birth": lambda f: f.date_between_dates(dt.date(1936, 1, 1), dt.date(2007, 12, 31)),
    "ssn": lambda f: f.ssn(),
    "company": lambda f: f.company(),
    "job": lambda f: f.job(),
    "ip": lambda f: f.ipv4_public(),
    "credit_card": lambda f: f.credit_card_number(),
    "iban": lambda f: f.iban(),
    "url": lambda f: f.url(),
}
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


class DB:
    def __init__(self, url):
        u = urlparse(url)
        self.kind = u.scheme.split("+")[0]
        if self.kind == "sqlite":
            import sqlite3
            self.conn = sqlite3.connect(unquote(u.path[1:] if u.path.startswith("//") else u.path.lstrip("/")) or ":memory:")
            self.ph, self.q = "?", '"'
        elif self.kind in ("postgres", "postgresql"):
            import psycopg
            self.conn = psycopg.connect(url.replace("postgres://", "postgresql://", 1))
            self.ph, self.q = "%s", '"'
        elif self.kind == "mysql":
            import pymysql
            self.conn = pymysql.connect(host=u.hostname, port=u.port or 3306, user=unquote(u.username or ""),
                                        password=unquote(u.password or ""), database=u.path.lstrip("/"))
            self.ph, self.q = "%s", "`"
        else:
            raise SystemExit(f"error: unsupported database URL scheme {u.scheme!r}")

    def ident(self, name):
        return f"{self.q}{name}{self.q}"

    def tables(self):
        sql = {
            "sqlite": "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
            "mysql": "SELECT table_name FROM information_schema.tables "
                     "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'",
        }.get(self.kind, "SELECT table_name FROM information_schema.tables "
                         "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")
        cur = self.conn.cursor()
        cur.execute(sql)
        names = sorted(r[0] for r in cur.fetchall())
        cur.close()
        return names

    def columns(self, table):
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM {self.ident(table)} WHERE 1 = 0")
        cols = [d[0] for d in cur.description]
        cur.close()
        return cols

    def rows(self, table, cols):
        cur = self.conn.cursor()
        cur.execute(f"SELECT {', '.join(self.ident(c) for c in cols)} FROM {self.ident(table)}")
        while batch := cur.fetchmany(BATCH):
            yield from batch
        cur.close()

    def insert(self, table, cols, rows):
        sql = (f"INSERT INTO {self.ident(table)} ({', '.join(self.ident(c) for c in cols)}) "
               f"VALUES ({', '.join([self.ph] * len(cols))})")
        cur = self.conn.cursor()
        cur.executemany(sql, rows)
        cur.close()

    def count(self, table):
        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {self.ident(table)}")
        n = cur.fetchone()[0]
        cur.close()
        return n


def copy_sqlite_schema(src, dst):
    cur = src.conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
                "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END")
    for (sql,) in cur.fetchall():
        dst.conn.execute(sql)
    dst.conn.commit()


def load_config(path):
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    config.setdefault("drop_tables", [])
    for table, spec in config["tables"].items():
        spec.setdefault("identity", [])
        spec.setdefault("fields", {})
        spec.setdefault("lookups", {})
        spec.setdefault("keep", [])
        spec.setdefault("drop", [])
        if any(f.get("analytics") for f in spec["fields"].values()) and not spec["identity"]:
            raise SystemExit(f"error: {table} has analytics fields but no identity columns")
        for col, lk in spec["lookups"].items():
            parent = lk["references"].split(".")[0]
            if parent not in config["tables"]:
                raise SystemExit(f"error: {table}.{col} points at {parent}, which isn't anonymized; "
                                 f"drop {table}.{col} too, or anonymize {parent}")
    return config


def plan(config):
    lines = ["# Anonymization plan", "",
             "The output is a descoped copy for analytics, not a working copy of the application.", ""]
    for table, spec in config["tables"].items():
        unredacted = list(spec["keep"])
        random_ = [f"{c} ({f['pii']})" for c, f in spec["fields"].items() if not f.get("analytics")]
        seeded = [f"{c} ({f['pii']}{', real year kept' if f.get('keep_year') else ''})"
                  for c, f in spec["fields"].items() if f.get("analytics")]
        for col, lk in spec["lookups"].items():
            seeded.append(f"{col} (points at {lk['references']})")
            seeded += [f"{c} (copied from {lk['references'].split('.')[0]}.{p})" for c, p in lk.get("copy", {}).items()]
        dropped = list(spec["drop"])
        lines += [f"## {table}", ""]
        if spec["identity"]:
            lines += [f"Records are identified by: {', '.join(spec['identity'])}", ""]
        for title, cols in (("Passes through unredacted", unredacted),
                            ("Random on every run", random_),
                            ("Same output for the same seed; relations kept", seeded),
                            ("Dropped (emptied)", dropped)):
            lines.append(f"- **{title}:** {', '.join(cols) if cols else 'none'}")
        lines.append("")
    lines += ["## Dropped tables (schema only, no rows)", "",
              ", ".join(config["drop_tables"]) if config["drop_tables"] else "none", ""]
    return "\n".join(lines)


def table_order(config):
    order, seen = [], set()

    def visit(t, path=()):
        if t in seen:
            return
        if t in path:
            raise SystemExit(f"error: lookup cycle through {t}")
        for ref in config["tables"][t]["lookups"].values():
            parent = ref["references"].split(".")[0]
            if parent != t:
                visit(parent, path + (t,))
        seen.add(t)
        order.append(t)

    for t in config["tables"]:
        visit(t)
    return order


def check_coverage(config, src):
    errors = []
    known = set(config["tables"]) | set(config["drop_tables"])
    present = src.tables()
    errors += [f"table {t}: not in config (add it to tables or drop_tables; when in doubt, drop it)"
               for t in present if t not in known]
    errors += [f"table {t}: in config but not in the database" for t in sorted(known) if t not in present]
    if errors:
        raise SystemExit("error: config doesn't cover the schema:\n  " + "\n  ".join(errors))
    for table, spec in config["tables"].items():
        cols = src.columns(table)
        listed = set(spec["fields"]) | set(spec["lookups"]) | set(spec["keep"]) | set(spec["drop"])
        for lk in spec["lookups"].values():
            listed |= set(lk.get("copy", {}))
        errors += [f"{table}.{c}: not in config (add it to fields, lookups, keep or drop)" for c in cols if c not in listed]
        errors += [f"{table}.{c}: in config but not in the table" for c in listed if c not in cols]
    if errors:
        raise SystemExit("error: config doesn't cover the schema:\n  " + "\n  ".join(errors))


def keep_year(table, col, original, fake):
    text = original.isoformat() if isinstance(original, dt.date) else str(original)
    if not (len(text) >= 10 and text[:4].isdigit() and text[4] == "-" and text[7] == "-"):
        raise SystemExit(f"error: {table}.{col} has a value that isn't an ISO date (YYYY-MM-DD); "
                         "standardize the source before anonymizing")
    year = int(text[:4])
    day = 28 if (fake.month, fake.day) == (2, 29) and not (year % 4 == 0 and (year % 100 or year % 400 == 0)) else fake.day
    return fake.replace(year=year, day=day)


def as_db_value(value, original):
    if isinstance(value, dt.date) and isinstance(original, str):
        return value.isoformat()
    return value


def anonymize(config, src, dst, seed):
    from faker import Faker

    faker = Faker(config.get("locale", "en_US"))
    referenced = {}
    for spec in config["tables"].values():
        for lk in spec["lookups"].values():
            referenced.setdefault(tuple(lk["references"].split(".")), {})
    report = {}

    for table in table_order(config):
        spec = config["tables"][table]
        cols = src.columns(table)
        idx = {c: i for i, c in enumerate(cols)}
        stats = {"rows": 0, "fresh_identity_fallback": 0, "orphan_lookups": 0}
        out_batch = []
        for row in src.rows(table, cols):
            row = list(row)
            new = list(row)
            identity = [row[idx[c]] for c in spec["identity"]]
            if spec["identity"] and all(v in (None, "") for v in identity):
                det = Persona(faker, secrets.token_bytes(32))
                stats["fresh_identity_fallback"] += 1
            else:
                det = Persona(faker, record_key(seed, spec.get("entity", table), identity))
            fresh = Persona(faker, secrets.token_bytes(32))
            for col, field in spec["fields"].items():
                if row[idx[col]] is None:
                    continue
                persona = det if field.get("analytics") else fresh
                value = persona.get(field["pii"])
                if field.get("keep_year"):
                    value = keep_year(table, col, row[idx[col]], value)
                new[idx[col]] = as_db_value(value, row[idx[col]])
            for col in spec["drop"]:
                new[idx[col]] = spec.get("drop_value")
            for col, lk in spec["lookups"].items():
                old = row[idx[col]]
                if old is None:
                    continue
                parent_row = referenced[tuple(lk["references"].split("."))].get(str(old))
                if parent_row is None:
                    stats["orphan_lookups"] += 1
                    new[idx[col]] = None
                    for c in lk.get("copy", {}):
                        new[idx[c]] = None
                    continue
                pcol = lk["references"].split(".")[1]
                new[idx[col]] = parent_row[pcol]
                for c, parent_col in lk.get("copy", {}).items():
                    new[idx[c]] = parent_row[parent_col]
            for key, mapping in referenced.items():
                if key[0] == table:
                    mapping[str(row[idx[key[1]]])] = dict(zip(cols, new))
            out_batch.append(new)
            stats["rows"] += 1
            if len(out_batch) >= BATCH:
                dst.insert(table, cols, out_batch)
                out_batch = []
        if out_batch:
            dst.insert(table, cols, out_batch)
        dst.conn.commit()
        report[table] = stats
    return report


def verify(config, src, dst):
    result, ok = {}, True
    for table, spec in config["tables"].items():
        cols = src.columns(table)
        r = {"same_columns": cols == dst.columns(table),
             "rows_source": src.count(table), "rows_target": dst.count(table)}
        idx = {c: i for i, c in enumerate(cols)}
        unchanged = {c: 0 for c in spec["fields"]}
        for a, b in zip(src.rows(table, cols), dst.rows(table, cols)):
            for c in spec["fields"]:
                if a[idx[c]] is not None and str(a[idx[c]]) == str(b[idx[c]]):
                    unchanged[c] += 1
        r["pii_values_unchanged"] = {c: n for c, n in unchanged.items() if n}
        orphans = {}
        for col, lk in spec["lookups"].items():
            pt, pc = lk["references"].split(".")
            parent = {str(v[0]) for v in dst.rows(pt, [pc])}
            orphans[col] = sum(1 for (v,) in dst.rows(table, [col]) if v is not None and str(v) not in parent)
        r["lookups_not_found"] = {c: n for c, n in orphans.items() if n}
        r["passed"] = r["same_columns"] and r["rows_source"] == r["rows_target"] and not r["lookups_not_found"]
        ok &= r["passed"]
        result[table] = r
    return ok, result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--source", help="sqlite:///path, postgresql://..., mysql://...")
    ap.add_argument("--target", help="same forms; must have the same schema and no rows")
    ap.add_argument("--plan", action="store_true", help="print what happens to every column and exit")
    ap.add_argument("--seed-env", default="ANON_SEED", help="env var holding the injected seed")
    ap.add_argument("--verify", action="store_true", help="check the target afterwards (counts only)")
    args = ap.parse_args()
    if args.plan:
        print(plan(load_config(args.config)))
        return
    if not (args.source and args.target):
        ap.error("--source and --target are required unless --plan is given")

    raw = os.environ.get(args.seed_env, "")
    if len(raw) < 32:
        raise SystemExit(f"error: set {args.seed_env} to a secret of at least 32 characters")
    config = load_config(args.config)
    src, dst = DB(args.source), DB(args.target)
    check_coverage(config, src)
    if dst.kind == "sqlite" and src.kind == "sqlite":
        copy_sqlite_schema(src, dst)
    for table in list(config["tables"]) + config["drop_tables"]:
        if src.columns(table) != dst.columns(table):
            raise SystemExit(f"error: target table {table} doesn't have the source's columns")
        if dst.count(table):
            raise SystemExit(f"error: target table {table} isn't empty")

    report = {"anonymized": anonymize(config, src, dst, raw.encode())}
    ok = True
    if args.verify:
        ok, report["verify"] = verify(config, src, dst)
    json.dump(report, sys.stdout, indent=2, default=str)
    print()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
