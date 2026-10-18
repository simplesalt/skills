#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
python3 "$root/tests/make_fixture_db.py" "$work/prod.db"
seed_a="$(printf 'seed-A-%.0s' {1..6})"
seed_b="$(printf 'seed-B-%.0s' {1..6})"
config="$root/assets/anonymize.config.example.json"

run_py() { ANON_SEED="$2" python3 "$root/templates/python/anonymize.py" --config "$config" \
  --source "sqlite:///$work/prod.db" --target "sqlite:///$work/$1.db" --verify > "$work/$1.json"; }

run_py py_a1 "$seed_a"; run_py py_a2 "$seed_a"; run_py py_b1 "$seed_b"
langs="py"
if command -v npm > /dev/null; then
  mkdir -p "$work/js" && cp "$root/templates/javascript/"{anonymize.mjs,package.json} "$work/js/"
  (cd "$work/js" && npm install --silent --no-audit --no-fund > /dev/null)
  run_js() { (cd "$work/js" && ANON_SEED="$2" node --no-warnings anonymize.mjs --config "$config" \
    --source "sqlite:///$work/prod.db" --target "sqlite:///$work/$1.db" --verify > "$work/$1.json"); }
  run_js js_a1 "$seed_a"; run_js js_a2 "$seed_a"; run_js js_b1 "$seed_b"
  langs="py js"
fi
python3 "$root/tests/check_properties.py" "$work" $langs

python3 - "$config" "$work/keep_year.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c["tables"]["customers"]["fields"]["birth_date"]["keep_year"] = True
json.dump(c, open(sys.argv[2], "w"))
PY
cp "$work/prod.db" "$work/messy.db"
python3 -c "import sqlite3,sys; d=sqlite3.connect(sys.argv[1]); d.execute(\"UPDATE customers SET birth_date='Wednesday, October 3rd, 1938' WHERE customer_id=2\"); d.commit()" "$work/messy.db"
for lang in $langs; do
  if [ "$lang" = py ]; then
    run() { ANON_SEED="$seed_a" python3 "$root/templates/python/anonymize.py" --config "$work/keep_year.json" --source "sqlite:///$work/$1.db" --target "sqlite:///$work/$2.db"; }
  else
    run() { (cd "$work/js" && ANON_SEED="$seed_a" node --no-warnings anonymize.mjs --config "$work/keep_year.json" --source "sqlite:///$work/$1.db" --target "sqlite:///$work/$2.db"); }
  fi
  run prod "${lang}_year" > /dev/null
  python3 - "$work/prod.db" "$work/${lang}_year.db" "$lang" <<'PY'
import sqlite3, sys
a = [r[0] for r in sqlite3.connect(sys.argv[1]).execute("SELECT birth_date FROM customers ORDER BY customer_id")]
b = [r[0] for r in sqlite3.connect(sys.argv[2]).execute("SELECT birth_date FROM customers ORDER BY customer_id")]
same_year = sum(x[:4] == y[:4] for x, y in zip(a, b))
same_date = sum(x == y for x, y in zip(a, b))
ok = same_year == len(a) and same_date < len(a) * 0.01
print(f"{sys.argv[3]}: {'ok  ' if ok else 'FAIL'} keep_year: {same_year}/{len(a)} years kept, {same_date} full dates unchanged by chance")
sys.exit(0 if ok else 1)
PY
  if run messy "${lang}_messy" > /dev/null 2> "$work/${lang}_messy.err"; then
    echo "$lang: FAIL messy birth date was accepted"; exit 1
  else
    echo "$lang: ok   messy birth date stops the run: $(tail -1 "$work/${lang}_messy.err")"
  fi
done
python3 - "$config" "$work" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
u = json.loads(json.dumps(c)); u["drop_tables"].remove("app_settings")
json.dump(u, open(f"{sys.argv[2]}/unlisted.json", "w"))
l = json.loads(json.dumps(c)); l["tables"]["newsletter"]["lookups"]["email"]["references"] = "user_logins.login_id"
json.dump(l, open(f"{sys.argv[2]}/to_dropped.json", "w"))
PY
for lang in $langs; do
  if [ "$lang" = py ]; then
    anon() { ANON_SEED="$seed_a" python3 "$root/templates/python/anonymize.py" "$@"; }
  else
    anon() { (cd "$work/js" && ANON_SEED="$seed_a" node --no-warnings anonymize.mjs "$@"); }
  fi
  anon --config "$config" --plan > "$work/${lang}_plan.md"
  if grep -q '^## customers' "$work/${lang}_plan.md" && grep -q 'user_logins, app_settings' "$work/${lang}_plan.md" \
     && grep -q 'Random on every run:\*\* phone (phone)' "$work/${lang}_plan.md"; then
    echo "$lang: ok   --plan lists every table and the dropped tables"
  else
    echo "$lang: FAIL --plan output"; cat "$work/${lang}_plan.md"; exit 1
  fi
  if anon --config "$work/unlisted.json" --source "sqlite:///$work/prod.db" --target "sqlite:///$work/${lang}_unlisted.db" \
       > /dev/null 2> "$work/${lang}_unlisted.err" || ! grep -q 'table app_settings: not in config' "$work/${lang}_unlisted.err"; then
    echo "$lang: FAIL unlisted table was accepted"; exit 1
  else
    echo "$lang: ok   unlisted table stops the run: $(grep app_settings "$work/${lang}_unlisted.err" | sed 's/^ *//')"
  fi
  if anon --config "$work/to_dropped.json" --plan > /dev/null 2> "$work/${lang}_to_dropped.err"; then
    echo "$lang: FAIL lookup into a dropped table was accepted"; exit 1
  else
    echo "$lang: ok   lookup into a dropped table stops the run: $(tail -1 "$work/${lang}_to_dropped.err")"
  fi
done
echo "work files in $work"
