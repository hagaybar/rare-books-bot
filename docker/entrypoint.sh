#!/bin/bash
set -e

echo "[entrypoint] Starting rare-books container..."

# Ensure data directories exist on the mounted volume
mkdir -p /app/data/index
mkdir -p /app/data/chat
mkdir -p /app/data/auth
mkdir -p /app/data/qa
mkdir -p /app/data/normalization/place_aliases
mkdir -p /app/data/normalization/publisher_aliases
mkdir -p /app/data/normalization/agent_aliases
mkdir -p /app/data/enrichment
mkdir -p /app/data/metadata
mkdir -p /app/data/m2
mkdir -p /app/data/canonical

# Seed admin user on first run (if auth.db has no users)
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
    USER_COUNT=$(python -c "
import sqlite3
from pathlib import Path
db = Path('data/auth/auth.db')
if not db.exists():
    print('0')
else:
    conn = sqlite3.connect(str(db))
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    print(count)
" 2>/dev/null || echo "0")

    if [ "$USER_COUNT" = "0" ]; then
        echo "[entrypoint] No users found. Creating admin user..."
        python -m app.cli create-user "$ADMIN_EMAIL" "$ADMIN_PASSWORD" --role admin
        echo "[entrypoint] Admin user created."
    else
        echo "[entrypoint] Users exist ($USER_COUNT). Skipping admin seed."
    fi
else
    echo "[entrypoint] ADMIN_EMAIL/ADMIN_PASSWORD not set. Skipping admin seed."
fi

echo "[entrypoint] Launching supervisord..."
exec supervisord -c /etc/supervisord.conf
