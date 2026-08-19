#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/storage
    chown -R app:app /app/storage
    exec gosu app "$@"
fi

exec "$@"
