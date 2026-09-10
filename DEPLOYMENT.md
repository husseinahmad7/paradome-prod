# ParaDome deployment runbook

Production uses Python 3.12 and `paradome.settings.production`. That settings
module fails closed when a required environment variable is absent; it never
falls back to a repository value.

## Before the first hardened release

1. Take timestamped MySQL and media backups and verify both can be read.
2. Retain a repository bundle before the planned history rewrite.
3. After the rewrite, deploy from a fresh clone. Do not pull the rewritten
   branch into an old server clone.
4. Rotate every credential that has existed in Git history. Removing a value
   from Git does not revoke it. Database rotation remains an explicit open
   incident until the live database credential is changed.

## Environment file

Copy `.env.example` to a file outside the checkout, for example
`/home/<account>/.config/paradome.env`, fill it from the password manager, and
set its mode to `0600`. Never paste values into source, templates, task logs, or
shell history.

The production file must define:

- Django host, CSRF, site URL, and secret-key settings;
- MySQL host, port, database, user, and password;
- SMTP host, account, password, sender, and contact recipient;
- all four Pusher settings;
- `DEMO_ACCOUNT_ENABLED`, `DEMO_USERNAME`, and `DEMO_DOME_SLUG`;
- an absolute `PRIVATE_MEDIA_ROOT` outside any directly served directory.

Set `DJANGO_SETTINGS_MODULE=paradome.settings.production` and
`PARADOME_ENV_FILE` in the PythonAnywhere WSGI configuration before the
application import. Remove any legacy assignment to `paradome.settings`.
Configure `/static/` to point at the release's `static_files` directory. Do not
add a web-server mapping for `PRIVATE_MEDIA_ROOT`.

## Release procedure

Create a fresh Python 3.12 virtual environment, then run from the release root:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements-production.txt
python manage.py check --deploy --settings=paradome.settings.production
python manage.py migrate --noinput --settings=paradome.settings.production
python manage.py createcachetable --settings=paradome.settings.production
python manage.py collectstatic --clear --noinput --settings=paradome.settings.production
```

Run data-cleanup commands in dry-run mode and inspect their reports before any
`--apply` invocation. Back up the database immediately before constraint or
rich-text cleanup migrations.

Point the PythonAnywhere web app at the fresh release/virtual environment,
reload it, and verify `/health/`. Then smoke-test the portfolio, authentication,
private Dome access, protected media, chat authorization, and demo restrictions.

## Demo reset task

After the demo management command ships, schedule this once daily at 00:00 UTC
with the same external environment file and production settings:

```sh
python manage.py reset_demo_sandbox --settings=paradome.settings.production
```

The task must remain idempotent. Alert on a non-zero exit instead of retrying
concurrently.

## Docker deployment

Fill a local untracked `.env`, then run `docker compose up --build`. This is a
production-mode stack and must sit behind a TLS-terminating proxy that sends
`X-Forwarded-Proto: https`; it is not intended to serve HTTPS directly on port
8000. The web container runs as an unprivileged user, waits for healthy MySQL,
applies migrations, creates the shared cache table, collects fingerprinted
static assets, and starts Gunicorn. MySQL, public migration media, protected
media, and collected static files use named volumes. Use
`docker-compose.debug.yml` for direct local HTTP development.

## Rollback

Keep the previous release directory, database snapshot, and media snapshot until
the smoke tests pass. To roll back, stop traffic, restore the matching database
and media snapshots, select the prior release and virtual environment, reload,
and repeat the smoke tests. Never run old code against a schema migrated beyond
that release unless the migration is documented as backwards-compatible.
