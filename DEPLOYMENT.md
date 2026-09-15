# ParaDome production deployment runbook

Production uses Python 3.12 and `paradome.settings.production`. The settings
module fails closed when required configuration is absent and loads its values
only from the process environment or a mode-`0600` environment file outside
the checkout.

## Release and backup layout

Keep immutable releases separate from mutable data. A recommended
PythonAnywhere layout is:

```text
/home/<account>/apps/paradome/
├── current -> releases/<release-id>
├── releases/
│   └── <release-id>/
│       ├── app/
│       └── venv/
└── shared/
    ├── backups/<backup-id>/
    ├── legacy_media/
    └── private_media/
/home/<account>/.config/paradome.env
```

`PRIVATE_MEDIA_ROOT` must name `shared/private_media` (or another absolute,
non-public directory), never a path inside a release. The legacy media source
must also be an absolute directory outside the fresh checkout. Releases must
not share a writable source tree.

Before changing code, schema, data, media, WSGI, or scheduled tasks, create one
timestamped backup set containing:

- a verified MySQL logical dump;
- the complete legacy-media and private-media trees, with metadata;
- the current WSGI file, Web-tab static mappings, and scheduled-task command;
- the external environment file, stored in the password manager or encrypted
  backup system rather than the release bundle;
- a repository bundle and the exact current release commit ID.

Verify that the dump can be listed/restored and that both media archives can be
read before proceeding. Keep the previous release and the complete matching
backup set until the rollback window closes. Retain the previous release
directory in full, including its release-specific `venv/`, for the same
period. Never reuse a virtual environment between release IDs.

Deploy only after the repository-history rewrite and full-history secret scan
have passed. Rotate every credential that has appeared in Git; removing it from
history does not revoke it. Database credential rotation remains an open
incident until the live database credential is changed.

## Required environment names

Copy `.env.example` to `/home/<account>/.config/paradome.env`, fill it from the
password manager, and set mode `0600`. Never paste values into source,
templates, task output, command history, or this runbook.

The production environment file contains these names:

```text
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
PUBLIC_SITE_URL
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
DB_CONN_MAX_AGE
DB_CONNECT_TIMEOUT
EMAIL_HOST
EMAIL_PORT
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
EMAIL_USE_TLS
EMAIL_USE_SSL
DEFAULT_FROM_EMAIL
SERVER_EMAIL
CONTACT_RECIPIENT
PUSHER_APP_ID
PUSHER_KEY
PUSHER_SECRET
PUSHER_CLUSTER
DEMO_ACCOUNT_ENABLED
DEMO_USERNAME
PRIVATE_MEDIA_ROOT
CACHE_TABLE
CACHE_TIMEOUT
CACHE_MAX_ENTRIES
SECURE_HSTS_SECONDS
```

Every production management command must carry both of these prefixes rather
than relying on an interactive shell's ambient state:

```sh
PARADOME_ENV_FILE="/home/<account>/.config/paradome.env" \
DJANGO_SETTINGS_MODULE="paradome.settings.production" \
"/home/<account>/apps/paradome/current/venv/bin/python" \
"/home/<account>/apps/paradome/current/app/manage.py" COMMAND
```

The examples below abbreviate the environment-and-interpreter portion as
`PRODUCTION_PREFIX`; replace the abbreviation with all four lines above when
executing a command. It is documentation notation, not a shell variable to
define.

## Fresh release procedure

1. Create the verified backup set above and record the deployed commit ID.
2. Create a new `releases/<release-id>/` directory and clone the rewritten
   repository into its `app/` child. Never pull rewritten history into an
   existing server clone.
3. Create a fresh Python 3.12 virtual environment at
   `releases/<release-id>/venv/` and install the adjacent
   `app/requirements-production.txt` with that environment's Python.
4. Before cutover, substitute the new release's explicit `app/` and `venv/`
   paths for `current/app/` and `current/venv/` in `PRODUCTION_PREFIX`, then
   run:

   ```sh
   PRODUCTION_PREFIX check --deploy
   PRODUCTION_PREFIX makemigrations --check --dry-run
   PRODUCTION_PREFIX sanitize_rich_text --dry-run
   PRODUCTION_PREFIX migrate_private_media --dry-run \
       --source-root "/home/<account>/apps/paradome/shared/legacy_media"
   ```

   Stop if either dry run reports a missing reference or unexpected rewrite.
   `--source-root` must be an existing absolute directory and must not equal
   `PRIVATE_MEDIA_ROOT`.
5. With the site in maintenance mode and the backup timestamp recorded, run:

   ```sh
   PRODUCTION_PREFIX migrate --noinput
   PRODUCTION_PREFIX createcachetable
   PRODUCTION_PREFIX sanitize_rich_text --apply
   PRODUCTION_PREFIX migrate_private_media --apply \
       --source-root "/home/<account>/apps/paradome/shared/legacy_media"
   PRODUCTION_PREFIX migrate_private_media --dry-run \
       --source-root "/home/<account>/apps/paradome/shared/legacy_media"
   PRODUCTION_PREFIX collectstatic --clear --noinput
   PRODUCTION_PREFIX reset_demo_sandbox
   ```

   The final media dry run must report zero files to copy, all referenced files
   already private, and zero missing files. Compare representative source and
   destination file hashes. `migrate_private_media` copies only: it never
   removes or mutates the source tree, and a missing reference aborts before
   the first copy. Retain the source tree through the rollback window.
6. Atomically repoint the single `current` symlink to the new release
   directory. Because that directory contains both `app/` and `venv/`, code
   and dependencies move together. Keep the Web tab and WSGI configuration on
   the stable `current/app/` and `current/venv/` paths, reload, and verify
   `/health/`.
7. Smoke-test the portfolio, authentication, private-Dome authorization,
   protected media, private chat, and demo restrictions before ending
   maintenance mode.

## PythonAnywhere WSGI and Web tab

The PythonAnywhere WSGI file must select the current release before importing
the application and must set production configuration explicitly:

```python
import os
import sys

release_root = "/home/<account>/apps/paradome/current/app"
if release_root not in sys.path:
    sys.path.insert(0, release_root)

os.environ["PARADOME_ENV_FILE"] = "/home/<account>/.config/paradome.env"
os.environ["DJANGO_SETTINGS_MODULE"] = "paradome.settings.production"

from paradome.wsgi import application
```

Point the virtualenv setting at
`/home/<account>/apps/paradome/current/venv`. Configure only `/static/` to
`/home/<account>/apps/paradome/current/app/static_files`. Remove every legacy
`/media/` Web-tab mapping before exposing the new release, and never map
`PRIVATE_MEDIA_ROOT`. User uploads are delivered only by object-authorized
Django routes.

## Locked daily maintenance at 00:00 UTC

Configure one PythonAnywhere daily task for exactly `00:00 UTC`. It cleans
expired rate-limit buckets and resets the demo sandbox under one non-blocking
host lock:

```sh
/usr/bin/flock -n "/home/<account>/apps/paradome/shared/daily-maintenance.lock" \
  /bin/sh -c 'cd "/home/<account>/apps/paradome/current/app" || exit 1; \
  cleanup_status=0; \
  PARADOME_ENV_FILE="/home/<account>/.config/paradome.env" \
  DJANGO_SETTINGS_MODULE="paradome.settings.production" \
  "/home/<account>/apps/paradome/current/venv/bin/python" \
  "/home/<account>/apps/paradome/current/app/manage.py" \
  cleanup_rate_limit_buckets --grace-seconds 86400 \
  --batch-size 1000 --max-batches 100 || cleanup_status=$?; \
  reset_status=0; \
  PARADOME_ENV_FILE="/home/<account>/.config/paradome.env" \
  DJANGO_SETTINGS_MODULE="paradome.settings.production" \
  "/home/<account>/apps/paradome/current/venv/bin/python" \
  "/home/<account>/apps/paradome/current/app/manage.py" \
  reset_demo_sandbox || reset_status=$?; \
  test "$cleanup_status" -eq 0 && test "$reset_status" -eq 0'
```

`cleanup_rate_limit_buckets` uses the indexed `expires_at` column and deletes
only rows whose expiration is strictly older than the configured grace period.
Its default grace is 24 hours, its minimum accepted grace is one hour, and each
run is capped at 100 batches of 1,000 rows unless the options above are changed.
It exits non-zero if the cap is reached while eligible rows remain; rerun it
under the same lock rather than removing the grace period or raising the batch
size above the command's validated maximum.

Both commands are idempotent. The shell records the cleanup result, always
runs the demo reset even if cleanup fails, then exits non-zero if either command
failed. Alert on any non-zero exit, including failure to acquire the lock; do
not launch a concurrent retry. Restrict the shared directory so only the
application account can create or replace the lock file.

## Rollback is snapshot-based

Schema constraints and rich-text sanitization are not treated as reversible.
After any migration or `--apply` command begins, a code-only rollback is
forbidden. Do not run reverse migrations or old code against the new schema
unless that exact path has been rehearsed and documented.

To roll back, stop traffic, restore the matching pre-release MySQL dump and
both media snapshots, restore the previous WSGI/Web-tab/task configuration,
atomically repoint `current` to the retained previous release directory, reload,
and repeat the smoke tests. That one symlink restores the matched code and
release-specific virtualenv together. Do not delete either previous artifact
until the rollback window closes. The copy-only legacy source is retained, but
it does not replace the requirement to restore the matched snapshot set.

## Docker deployment

Fill a local untracked `.env`, then run `docker compose up --build`. The stack
must sit behind a TLS-terminating proxy that sends `X-Forwarded-Proto: https`;
it does not terminate HTTPS on port 8000. The container runs unprivileged,
waits for healthy MySQL, applies migrations, creates the shared cache table,
collects fingerprinted static assets, and starts Gunicorn. Use
`docker-compose.debug.yml` only for direct local HTTP development.
