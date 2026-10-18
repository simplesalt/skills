#!/usr/bin/env python3
import sqlite3
import sys

DETERMINISTIC = ["full_name", "email", "street", "city", "state", "zip", "birth_date"]
CHANCE = {"state": 0.1, "zip": 0.01, "city": 0.01}


def main():
    work, langs = sys.argv[1], sys.argv[2:]
    prod = sqlite3.connect(f"{work}/prod.db")
    schema = lambda d: d.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
    failures = []
    for lang in langs:
        db = {n: sqlite3.connect(f"{work}/{lang}_{n}.db") for n in ("a1", "a2", "b1")}
        col = lambda n, c: [r[0] for r in db[n].execute(f"SELECT {c} FROM customers ORDER BY customer_id")]
        real = [r[0] for r in prod.execute("SELECT full_name FROM customers ORDER BY customer_id")]

        def check(ok, what):
            print(f"{lang}: {'ok  ' if ok else 'FAIL'} {what}")
            if not ok:
                failures.append(f"{lang}: {what}")

        check(all(schema(d) == schema(prod) for d in db.values()), "schema identical to source")
        for c in DETERMINISTIC:
            a, a2, b = col("a1", c), col("a2", c), col("b1", c)
            check(a == a2, f"{c}: same seed gives the same fakes")
            check(sum(x == y for x, y in zip(a, b)) <= CHANCE.get(c, 0.002) * len(a), f"{c}: other seed gives other fakes")
        check(sum(x == y for x, y in zip(col("a1", "phone"), col("a2", "phone"))) == 0, "phone (not analytics) fresh each run")
        check(all(v is None for v in col("a1", "notes")), "notes dropped")
        check(sum(x == y for x, y in zip(real, col("a1", "full_name"))) == 0, "no real name kept")
        d = db["a1"]
        check(d.execute("SELECT COUNT(*) FROM orders o JOIN customers c USING (customer_id) "
                        "WHERE o.ship_name = c.full_name AND o.ship_street = c.street").fetchone()[0] == 6000,
              "orders copy the customer's new name and street")
        q = "SELECT c.customer_id FROM newsletter n JOIN customers c ON c.email = n.email ORDER BY n.rowid"
        check(prod.execute(q).fetchall() == d.execute(q).fetchall(), "newsletter emails follow their customer")
        check(all(d.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in ("user_logins", "app_settings")),
              "dropped tables have no rows")
        real_emails = {r[0] for r in prod.execute("SELECT email FROM customers")}
        check(not any(r[0] in real_emails for r in d.execute("SELECT email FROM newsletter")), "no real email in newsletter")
    print("PASSED" if not failures else f"FAILED: {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
