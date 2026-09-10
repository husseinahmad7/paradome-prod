#!/bin/sh
set -eu

if [ "${PARADOME_SKIP_STARTUP_TASKS:-0}" != "1" ]; then
    python manage.py migrate --noinput
    python manage.py createcachetable
    python manage.py collectstatic --clear --noinput
fi

exec "$@"
