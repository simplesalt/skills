<!-- agent-prompt -->

# Field names that suggest PII

Match case-insensitively, on whole words or parts (`cust_email`, `EmailAddr`,
`billing_zip`). A match is a candidate to confirm with the user, not a verdict.

| PII type | Name patterns |
|---|---|
| `name` / `first_name` / `last_name` | name, full_name, first, fname, given, last, lname, surname, family, middle, maiden, nickname, display_name, contact, owner, recipient, ship_to, bill_to, signer, guardian, emergency_contact |
| `email` | email, e_mail, mail, email_addr, login (often an email), username (sometimes) |
| `phone` | phone, tel, telephone, mobile, cell, fax, sms, msisdn, whatsapp |
| `street_address` / `address` | address, addr, street, line1, line2, address1, apt, unit, suite, po_box, residence |
| `city` / `state` / `zip` / `country` | city, town, locality, state, province, region, county, zip, zipcode, postal, postcode, country (often fine to keep) |
| `date_of_birth` | dob, birth, birthday, birth_date, born, age (derived; usually keep coarse or fake) |
| `ssn` and national IDs | ssn, social, sin, nin, national_id, tax_id, tin, ein, passport, license, licence, driver, dl_number, voter, medicare, medicaid, mrn, patient_id (sometimes) |
| Financial | card, cc, pan, credit_card, iban, account_number, acct, routing, bank, swift |
| Online | ip, ip_address, mac, device_id, imei, idfa, gaid, cookie, user_agent, session, fingerprint |
| Location | lat, lng, lon, latitude, longitude, geo, coordinates, location, gps |
| `username` | username, user_name, handle, screen_name, login |
| Other personal | gender, sex, race, ethnicity, religion, marital, salary, income, photo, image, avatar, signature, biometric |

Unstructured, always `drop`: notes, note, comment, comments, description, desc,
message, body, text, remarks, memo, details, free_text, feedback, transcript,
reason, summary, any JSON or blob column whose contents the user can't vouch for.

Fields that often hide PII behind a neutral name, so ask about them: ref,
reference, external_id, legacy_id, code, extra, custom_*, attr*, field1..N,
data, metadata, payload, properties, tags, label, title, subject.

## Tables to drop whole

The output is for analytics, so most application plumbing has no place in it.
Propose `drop_tables` for these, and when in doubt, drop it:

- Identity and access: users/accounts used for login, logins, credentials,
  passwords, password_resets, sessions, tokens, api_keys, oauth_*, mfa_*,
  permissions, roles, invitations.
- Audit and logs: audit_log, events, activity, history, access_log,
  request_log, emails_sent, notifications, webhooks.
- Application metadata: settings, config, options, feature_flags, versions,
  schema_migrations, migrations, alembic_version, flyway_*, knex_*, jobs,
  queues, locks, cache.
- Small lookup and strings tables (translations, i18n, strings, labels,
  templates, email_templates, enum-style status tables). Keep one only if an
  analysis needs its labels, and check its text holds no names or emails.

If a kept table has a column that points at a dropped table, drop that column
too, or analysts get keys that lead nowhere. The script refuses a lookup into
a table it doesn't anonymize.

## Text columns that hold structured values

A column typed `TEXT`, `VARCHAR` or `CHAR` whose name says it's a date, a
number or a code (`birth_date`, `dob`, `zip`, `amount`, `phone`, `ssn`,
`created`, `year`) can hold anything: `03/10/1938`, `10-3-38`,
`Wednesday, October 3rd, 1938`, `82001-1234`, `n/a`. Faker replaces the whole
value, so the fake looks clean even when the source wasn't, and options that
read the original (`keep_year`) fail on it. Flag every such column to the user.
