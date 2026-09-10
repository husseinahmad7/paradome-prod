# ParaDome testing

## Local setup

Local development and tests use SQLite and inert email/Pusher defaults; no live
credentials are required.

```sh
python -m venv .venv
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test --settings=paradome.settings.test
```

Use `docker compose -f docker-compose.debug.yml up --build` for the equivalent
containerized development server.

## Required pre-merge checks

CI uses Python 3.12 and MySQL 8.4 to run model drift checks, Django production
and deployment checks, real MySQL migrations, the test suite, `pip-audit`, and a
full-history Gitleaks scan. The history scan is expected to remain red until the
planned repository-history rewrite removes the previously committed values.

For a production-settings check outside CI, provide a disposable non-production
environment and run:

```sh
python manage.py makemigrations --check --dry-run --settings=paradome.settings.production
python manage.py check --deploy --settings=paradome.settings.production
```

Never point tests at the live database, SMTP account, Pusher application, media
directory, or demo user.

## Release acceptance

- `/health/` returns `200` only when the database is reachable and never exposes
  exception or connection details.
- HTTPS responses include HSTS, CSP, frame denial, referrer, MIME-sniffing,
  Permissions-Policy, and cross-origin headers.
- Anonymous, outsider, member, moderator, owner, and demo authorization tests
  pass for every object-scoped route.
- State-changing GET requests return `405`; missing CSRF tokens are rejected.
- Stored rich-text attack payloads remain inert, and private files cannot be
  retrieved through a public media URL.
- Pusher authorization rejects non-members and realtime events contain IDs, not
  message HTML or content.
- Demo actions cannot affect real users or content, and the reset command can be
  run twice with the same result.
