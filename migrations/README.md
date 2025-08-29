# Migrations (notes)

This folder holds notes and scripts for future migrations (for example: SQLite -> PostgreSQL).

Currently the project runs on SQLite by default. The `db.py` module centralizes DB access and
is intentionally simple to make future backend swaps easier.

Planned files:

- `migrate_sqlite_to_postgres.py` — an idempotent script supporting `--dry-run` and `--apply` modes.

How to use (future)

1. Ensure you have a Postgres database and a `DATABASE_URL` ready.
2. Run the migration script in `dry-run` mode first:

```bash
python migrations/migrate_sqlite_to_postgres.py --database-url "$DATABASE_URL" --sqlite-file ./chat_settings.db --dry-run
```

3. Inspect the output. If everything looks good, run with `--apply`.

Notes
- Do a backup of `chat_settings.db` before running any migration.
- The migration script should be reviewed and tested on a staging server before production.
