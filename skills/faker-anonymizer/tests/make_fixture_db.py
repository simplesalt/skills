#!/usr/bin/env python3
import random
import sqlite3
import sys

from faker import Faker

SCHEMA = """
CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  full_name   TEXT NOT NULL,
  email       TEXT NOT NULL UNIQUE,
  phone       TEXT,
  street      TEXT,
  city        TEXT,
  state       TEXT,
  zip         TEXT,
  birth_date  TEXT,
  plan        TEXT NOT NULL,
  signup_date TEXT NOT NULL,
  notes       TEXT
);
CREATE TABLE orders (
  order_id    INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  ship_name   TEXT,
  ship_street TEXT,
  amount      REAL NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE TABLE newsletter (
  email         TEXT PRIMARY KEY REFERENCES customers(email),
  subscribed_at TEXT NOT NULL
);
CREATE TABLE user_logins (
  login_id      INTEGER PRIMARY KEY,
  customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
  password_hash TEXT NOT NULL,
  last_ip       TEXT,
  logged_in_at  TEXT NOT NULL
);
CREATE TABLE app_settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);
CREATE INDEX orders_by_customer ON orders(customer_id);
"""


def main():
    path = sys.argv[1]
    fake, rnd = Faker("en_US"), random.Random(3)
    Faker.seed(3)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    customers = [(1, "Joan Baez", "joan.baez@folkmail.example", "307-555-0142", "123 Main Street",
                  "Cheyenne", "Wyoming", "82001", "1941-01-09", "pro", "2023-04-02", "Prefers phone calls")]
    for i in range(2, 2001):
        name = fake.name()
        customers.append((i, name, fake.unique.email(), fake.phone_number(), fake.street_address(),
                          fake.city(), fake.state(), fake.zipcode(),
                          fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat(),
                          rnd.choice(["free", "pro", "team"]), fake.date_between("-3y", "-1d").isoformat(),
                          rnd.choice([None, f"Spoke with {name.split()[0]}", "VIP"])))
    db.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", customers)
    orders = []
    for i in range(1, 6001):
        c = rnd.choice(customers)
        orders.append((i, c[0], c[1], c[4], round(rnd.uniform(5, 500), 2),
                       fake.date_time_between("-1y", "now").isoformat(sep=" ", timespec="seconds")))
    db.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    subs = rnd.sample(customers, 700) + [customers[0]]
    db.executemany("INSERT OR IGNORE INTO newsletter VALUES (?,?)",
                   [(c[2], fake.date_between("-2y", "now").isoformat()) for c in subs])
    db.executemany("INSERT INTO user_logins VALUES (?,?,?,?,?)",
                   [(i, rnd.choice(customers)[0], fake.sha256(), fake.ipv4(),
                     fake.date_time_between("-30d", "now").isoformat(sep=" ", timespec="seconds"))
                    for i in range(1, 501)])
    db.executemany("INSERT INTO app_settings VALUES (?,?)",
                   [("schema_version", "42"), ("support_email", "help@folkmail.example")])
    db.commit()


if __name__ == "__main__":
    main()
