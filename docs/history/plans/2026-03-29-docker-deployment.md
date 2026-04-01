# Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Containerize the rare-books-bot app (FastAPI + React) for deployment to an Oracle Ampere A1 test server with a single deploy command.

**Architecture:** Single Docker container running nginx (SSL/static/proxy) + uvicorn (FastAPI) managed by supervisord. Data persists on a Docker volume mounted at `/app/data`. Deploy via rsync + ssh from developer laptop.

**Tech Stack:** Docker (multi-stage build), nginx, supervisord, Poetry, Node/Vite, bash

**Spec:** `docs/superpowers/specs/2026-03-29-docker-deployment-design.md`

---

## Pre-Requirements (User Must Complete Before Implementation)

Before running the implementation tasks, you need:

### On Your Local Machine
1. **Docker Desktop installed** with buildx support
   - Verify: `docker buildx version`
2. **SSH access to the Oracle A1 server** configured
   - Verify: `ssh <your-user>@<server-ip>` connects without issues
   - Note down: server IP, SSH username, SSH key path

### On the Oracle A1 Server
3. **Docker installed** on the ARM64 server
   - Install: `sudo apt-get update && sudo apt-get install docker.io`
   - Add your user to docker group: `sudo usermod -aG docker $USER`
   - Verify: `docker run hello-world`
4. **SSL certificate files** copied to `~/rare-books-certs/`
   - You need two files: the certificate (`.crt` or `.pem`) and private key (`.key`)
   - Note down: exact filenames (e.g., `fullchain.pem`, `privkey.pem`)
5. **DNS A record** pointing `cenlib-rare-books.nurdillo.com` to the server's public IP
   - Verify: `nslookup cenlib-rare-books.nurdillo.com` resolves to the server IP
6. **Firewall** allows inbound ports 80 and 443
   - Oracle Cloud: check Security List / Network Security Group in the VCN
   - On server: `sudo iptables -L -n | grep -E '80|443'`
7. **Environment file** created at `~/rare-books.env` with your values:
   ```
   OPENAI_API_KEY=sk-your-key-here
   JWT_SECRET=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
   CORS_ORIGIN=https://cenlib-rare-books.nurdillo.com
   HTTPS=true
   SESSIONS_DB_PATH=/app/data/chat/sessions.db
   BIBLIOGRAPHIC_DB_PATH=/app/data/index/bibliographic.db
   ADMIN_EMAIL=your-admin-username
   ADMIN_PASSWORD=your-admin-password-min-8-chars
   ```

### Information I Need From You
8. **Server SSH connection string** — e.g., `ubuntu@129.146.xx.xx` or `opc@129.146.xx.xx`
9. **SSH key path** — e.g., `~/.ssh/oracle_a1.pem` (or default `~/.ssh/id_rsa`)
10. **SSL cert filenames** — the exact names of your `.crt`/`.pem` and `.key` files in `~/rare-books-certs/`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `Dockerfile` | Create | Multi-stage build: node (frontend) + python (backend + nginx + supervisord) |
| `.dockerignore` | Create | Exclude dev files from Docker build context |
| `docker/nginx.conf` | Create | SSL termination, static files, reverse proxy, WebSocket upgrade |
| `docker/supervisord.conf` | Create | Process manager for nginx + uvicorn |
| `docker/entrypoint.sh` | Create | Container startup: directory init, admin seeding, launch supervisord |
| `deploy.sh` | Create | Semi-automated deploy script (rsync + ssh + docker build + health check) |
| `.gitignore` | Modify | Add `.superpowers/` directory |

---

## Task 1: .dockerignore

**Files:**
- Create: `.dockerignore`

- [ ] **Step 1: Create .dockerignore**

```
# Version control
.git
.gitignore

# Development
.venv
venv
node_modules
frontend/node_modules
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache

# IDE
.vscode
.idea
*.sublime-*

# Data (mounted as volume, not baked into image)
data/

# Docs and non-runtime files
docs/
archive/
audits/
reports/
tests/
*.md
!frontend/README.md

# OS
.DS_Store
Thumbs.db

# Env files
.env
.env.*
*.env

# Logs
logs/
*.log

# Babysitter / superpowers
.a5c/
.superpowers/

# Build artifacts
frontend/dist/
```

- [ ] **Step 2: Verify it exists**

Run: `cat .dockerignore | head -5`
Expected: First 5 lines of the file

- [ ] **Step 3: Commit**

```bash
git add .dockerignore
git commit -m "$(cat <<'EOF'
chore: add .dockerignore for Docker build context

Excludes dev files, data directory (mounted as volume), tests, docs,
IDE settings, and babysitter/superpowers artifacts from the build context.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: supervisord.conf

**Files:**
- Create: `docker/supervisord.conf`

- [ ] **Step 1: Create docker directory**

Run: `mkdir -p docker`

- [ ] **Step 2: Create supervisord.conf**

```ini
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
logfile_maxbytes=0
pidfile=/var/run/supervisord.pid

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:uvicorn]
command=uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 2
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
environment=PYTHONUNBUFFERED="1"
```

- [ ] **Step 3: Commit**

```bash
git add docker/supervisord.conf
git commit -m "$(cat <<'EOF'
chore: add supervisord config for Docker container

Manages nginx and uvicorn as child processes. Both log to stdout/stderr
so docker logs can capture all output. Uvicorn runs 2 workers on
127.0.0.1:8000 (internal only, nginx handles external traffic).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: nginx.conf

**Files:**
- Create: `docker/nginx.conf`

**Note:** The SSL cert/key filenames are placeholders (`cert.pem` / `key.pem`). These will be updated once the user provides the actual filenames. The deploy script will also need the correct filenames.

- [ ] **Step 1: Create nginx.conf**

```nginx
worker_processes auto;
error_log /dev/stderr warn;
pid /var/run/nginx.pid;

events {
    worker_connections 256;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent"';
    access_log /dev/stdout main;

    sendfile on;
    keepalive_timeout 65;
    client_max_body_size 10m;

    # Gzip compression for text assets
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # Redirect HTTP -> HTTPS
    server {
        listen 80;
        server_name cenlib-rare-books.nurdillo.com;
        return 301 https://$host$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl;
        server_name cenlib-rare-books.nurdillo.com;

        # SSL certificate (mounted from host)
        ssl_certificate /etc/ssl/certs/rare-books/cert.pem;
        ssl_certificate_key /etc/ssl/certs/rare-books/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # HSTS — only header nginx owns; other security headers are
        # set by FastAPI middleware (X-Frame-Options, CSP, etc.)
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # --- API routes: proxy to FastAPI ---
        # IMPORTANT: Routes that collide with SPA paths (/chat, /diagnostics)
        # are handled carefully — only API sub-paths are proxied.
        # Everything else falls through to the SPA catch-all at the bottom.

        # /chat — collision with SPA route.
        # POST /chat -> API. GET /chat -> SPA (browser navigation).
        # proxy_intercept_errors catches FastAPI's 405 for GET and serves SPA.
        location = /chat {
            proxy_pass http://127.0.0.1:8000;
            proxy_intercept_errors on;
            error_page 405 = @spa_fallback;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /chat/history -> API (no SPA collision)
        location /chat/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /auth/* -> API (no SPA collision — SPA uses /login, not /auth)
        location /auth {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /metadata/* -> API (no SPA collision)
        location /metadata {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /health* -> API
        location /health {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /diagnostics — collision with SPA routes /diagnostics/query and /diagnostics/db.
        # Only proxy specific API sub-paths. SPA paths fall to catch-all.
        # API paths: /diagnostics/query-run*, /diagnostics/labels*, /diagnostics/gold-set*,
        #            /diagnostics/tables*
        # SPA paths: /diagnostics/query, /diagnostics/db
        location /diagnostics/query-run {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /diagnostics/labels {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /diagnostics/gold-set {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /diagnostics/tables {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /sessions/* -> API
        location /sessions {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # /network — only proxy API sub-routes (GET /network is SPA)
        location /network/map {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /network/agent {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket — requires upgrade headers
        location /ws {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 86400;
            proxy_send_timeout 86400;
        }

        # --- SPA fallback (named location for error_page redirects) ---
        location @spa_fallback {
            root /app/frontend/dist;
            rewrite ^ /index.html break;
        }

        # --- Static frontend (React SPA) catch-all ---
        # All paths not matched above serve the SPA.
        # try_files serves static assets if they exist, else index.html.
        location / {
            root /app/frontend/dist;
            index index.html;
            try_files $uri $uri/ /index.html;
        }
    }
}
```

- [ ] **Step 2: Verify syntax is valid (basic check)**

Run: `head -20 docker/nginx.conf`
Expected: Shows the worker_processes and events block

- [ ] **Step 3: Commit**

```bash
git add docker/nginx.conf
git commit -m "$(cat <<'EOF'
chore: add nginx config for Docker deployment

SSL termination with existing cert files, HTTP->HTTPS redirect,
reverse proxy for all API routes to uvicorn :8000, WebSocket upgrade
headers for /ws, gzip compression, security headers (HSTS, X-Frame-Options),
and React SPA static file serving with try_files fallback.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: entrypoint.sh

**Files:**
- Create: `docker/entrypoint.sh`

- [ ] **Step 1: Create entrypoint.sh**

```bash
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
```

- [ ] **Step 2: Make executable**

Run: `chmod +x docker/entrypoint.sh`

- [ ] **Step 3: Commit**

```bash
git add docker/entrypoint.sh
git commit -m "$(cat <<'EOF'
chore: add Docker entrypoint script

Creates required data directories on the mounted volume, seeds an admin
user on first run if ADMIN_EMAIL/ADMIN_PASSWORD are set and auth.db has
no existing users, then launches supervisord to manage nginx + uvicorn.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# ==============================================================
# Stage 1: Build React frontend
# ==============================================================
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ==============================================================
# Stage 2: Python runtime + nginx + supervisord
# ==============================================================
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml poetry.lock ./

# Install Python dependencies (no dev deps, no virtualenv)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root

# Copy application code
COPY app/ app/
COPY scripts/ scripts/

# Copy frontend build from stage 1
COPY --from=frontend-builder /build/frontend/dist frontend/dist/

# Copy Docker config files
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisord.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Remove default nginx site
RUN rm -f /etc/nginx/sites-enabled/default

# Expose HTTP and HTTPS
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 2: Verify Dockerfile syntax**

Run: `head -30 Dockerfile`
Expected: Shows the frontend-builder stage

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "$(cat <<'EOF'
feat: add multi-stage Dockerfile for deployment

Stage 1: node:20-slim builds the React frontend (npm ci + npm run build).
Stage 2: python:3.12-slim installs Poetry deps, nginx, supervisord,
copies app code + frontend dist. WORKDIR is /app so relative data/ paths
resolve to the Docker volume mount. Health check hits /health endpoint.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: deploy.sh

**Files:**
- Create: `deploy.sh`

**Note:** The `SERVER_USER`, `SERVER_HOST`, and `SSH_KEY` variables at the top must be filled in with the user's actual values before first use. The SSL cert filenames in the docker run command (`cert.pem` / `key.pem`) must match the actual filenames in `~/rare-books-certs/` on the server.

- [ ] **Step 1: Create deploy.sh**

```bash
#!/bin/bash
set -euo pipefail

# =============================================================================
# Configuration — UPDATE THESE before first use
# =============================================================================
SERVER_USER="TODO_SET_ME"          # e.g., "ubuntu" or "opc"
SERVER_HOST="TODO_SET_ME"          # e.g., "129.146.xx.xx"
SSH_KEY="TODO_SET_ME"              # e.g., "~/.ssh/oracle_a1.pem"
SSL_CERT_FILE="cert.pem"          # Filename in ~/rare-books-certs/
SSL_KEY_FILE="key.pem"            # Filename in ~/rare-books-certs/

# Derived
SSH_CMD="ssh -i $SSH_KEY $SERVER_USER@$SERVER_HOST"
REMOTE_SRC="~/rare-books-bot"
REMOTE_DATA="~/rare-books-data"
IMAGE_NAME="rare-books"
CONTAINER_NAME="rare-books"
DOMAIN="cenlib-rare-books.nurdillo.com"
LOCAL_DB="data/index/bibliographic.db"

# =============================================================================
# Parse arguments
# =============================================================================
ACTION="deploy"
UPDATE_DB=false

for arg in "$@"; do
    case $arg in
        --update-db)  UPDATE_DB=true ;;
        --db-only)    ACTION="db-only" ;;
        --rollback)   ACTION="rollback" ;;
        --help|-h)    ACTION="help" ;;
        *)            echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

if [ "$ACTION" = "help" ]; then
    echo "Usage: ./deploy.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (none)        Deploy code only (rsync + build + restart)"
    echo "  --update-db   Deploy code + copy fresh bibliographic.db"
    echo "  --db-only     Copy bibliographic.db without rebuilding container"
    echo "  --rollback    Restart container with previous image tag"
    echo "  --help        Show this message"
    exit 0
fi

# =============================================================================
# Validate configuration
# =============================================================================
if [[ "$SERVER_USER" == "TODO_SET_ME" || "$SERVER_HOST" == "TODO_SET_ME" || "$SSH_KEY" == "TODO_SET_ME" ]]; then
    echo "ERROR: Edit deploy.sh and set SERVER_USER, SERVER_HOST, and SSH_KEY first."
    exit 1
fi

# =============================================================================
# Functions
# =============================================================================
health_check() {
    echo "--- Health check ---"
    for i in 1 2 3; do
        sleep 5
        if $SSH_CMD "curl -sf http://127.0.0.1:8000/health" > /dev/null 2>&1; then
            echo "Health check PASSED (attempt $i)"
            echo "Site live at: https://$DOMAIN"
            return 0
        fi
        echo "Health check attempt $i failed, retrying..."
    done
    echo "ERROR: Health check FAILED after 3 attempts"
    echo "Check logs: $SSH_CMD \"docker logs $CONTAINER_NAME --tail 50\""
    return 1
}

sync_code() {
    echo "--- Syncing source code to server ---"
    rsync -avz --delete \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='frontend/node_modules' \
        --exclude='__pycache__' \
        --exclude='.venv' \
        --exclude='venv' \
        --exclude='data/' \
        --exclude='logs/' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='*.env' \
        --exclude='.a5c/cache/' \
        --exclude='.a5c/node_modules/' \
        --exclude='.a5c/runs/' \
        --exclude='.superpowers/' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.mypy_cache' \
        --exclude='.ruff_cache' \
        --exclude='tests/' \
        --exclude='docs/' \
        --exclude='archive/' \
        --exclude='audits/' \
        --exclude='reports/' \
        --exclude='frontend/dist/' \
        -e "ssh -i $SSH_KEY" \
        ./ "$SERVER_USER@$SERVER_HOST:$REMOTE_SRC/"
}

sync_db() {
    echo "--- Copying bibliographic.db to server ---"
    if [ ! -f "$LOCAL_DB" ]; then
        echo "ERROR: $LOCAL_DB not found locally"
        exit 1
    fi
    $SSH_CMD "mkdir -p $REMOTE_DATA/index"
    scp -i "$SSH_KEY" "$LOCAL_DB" "$SERVER_USER@$SERVER_HOST:$REMOTE_DATA/index/bibliographic.db"
    echo "Database copied."
}

build_and_run() {
    echo "--- Building and starting container on server ---"
    GIT_SHA=$(git rev-parse --short HEAD)

    $SSH_CMD << REMOTE_SCRIPT
set -euo pipefail
cd $REMOTE_SRC

# Build with git SHA tag
docker build -t $IMAGE_NAME:$GIT_SHA -t $IMAGE_NAME:latest .

# Record previous image for rollback
PREV_TAG=\$(docker inspect $CONTAINER_NAME --format='{{.Config.Image}}' 2>/dev/null | sed 's/.*://' || echo "none")
echo "\$PREV_TAG" > ~/rare-books-prev-tag

# Stop and remove old container
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Start new container
docker run -d \
    --name $CONTAINER_NAME \
    --restart unless-stopped \
    --env-file ~/rare-books.env \
    -v $REMOTE_DATA:/app/data \
    -v ~/rare-books-certs/$SSL_CERT_FILE:/etc/ssl/certs/rare-books/cert.pem:ro \
    -v ~/rare-books-certs/$SSL_KEY_FILE:/etc/ssl/certs/rare-books/key.pem:ro \
    -p 80:80 \
    -p 443:443 \
    $IMAGE_NAME:$GIT_SHA

echo "Container started with image $IMAGE_NAME:$GIT_SHA"
REMOTE_SCRIPT
}

rollback() {
    echo "--- Rolling back to previous image ---"
    $SSH_CMD << REMOTE_SCRIPT
set -euo pipefail

PREV_TAG=\$(cat ~/rare-books-prev-tag 2>/dev/null || echo "")
if [ -z "\$PREV_TAG" ] || [ "\$PREV_TAG" = "none" ]; then
    echo "ERROR: No previous image tag found. Cannot rollback."
    exit 1
fi

echo "Rolling back to $IMAGE_NAME:\$PREV_TAG"

docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

docker run -d \
    --name $CONTAINER_NAME \
    --restart unless-stopped \
    --env-file ~/rare-books.env \
    -v $REMOTE_DATA:/app/data \
    -v ~/rare-books-certs/$SSL_CERT_FILE:/etc/ssl/certs/rare-books/cert.pem:ro \
    -v ~/rare-books-certs/$SSL_KEY_FILE:/etc/ssl/certs/rare-books/key.pem:ro \
    -p 80:80 \
    -p 443:443 \
    $IMAGE_NAME:\$PREV_TAG

echo "Rolled back to $IMAGE_NAME:\$PREV_TAG"
REMOTE_SCRIPT
}

# =============================================================================
# Main
# =============================================================================
echo "=== Rare Books Deploy ==="
echo "Server: $SERVER_USER@$SERVER_HOST"
echo "Action: $ACTION"
echo ""

case $ACTION in
    deploy)
        sync_code
        if [ "$UPDATE_DB" = true ]; then
            sync_db
        fi
        build_and_run
        health_check
        ;;
    db-only)
        sync_db
        echo "Database updated. Container not rebuilt."
        echo "Restart container to pick up new DB: $SSH_CMD \"docker restart $CONTAINER_NAME\""
        ;;
    rollback)
        rollback
        health_check
        ;;
esac

echo ""
echo "=== Done ==="
```

- [ ] **Step 2: Make executable**

Run: `chmod +x deploy.sh`

- [ ] **Step 3: Commit**

```bash
git add deploy.sh
git commit -m "$(cat <<'EOF'
feat: add semi-automated deploy script

deploy.sh runs from developer laptop to deploy to Oracle A1 server:
- rsync source code (excludes data/, node_modules, .git, tests, etc.)
- docker build with git SHA tagging on server
- container restart with env-file, data volume, and SSL cert mounts
- health check with 3 retries

Supports 4 modes: code-only (default), --update-db (code + fresh
bibliographic.db), --db-only (just DB, no rebuild), --rollback
(restart with previous image tag).

Configuration section at top must be filled in before first use.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: .gitignore update

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add .superpowers/ to .gitignore**

Append to the end of `.gitignore`:

```
# Superpowers brainstorming artifacts
.superpowers/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "$(cat <<'EOF'
chore: add .superpowers/ to .gitignore

Brainstorming session artifacts should not be committed.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Local Docker Build Test

This task validates the Dockerfile builds correctly on your local machine before deploying.

- [ ] **Step 1: Build the image locally**

Run: `docker build -t rare-books:test .`
Expected: Build completes successfully (may take 3-5 minutes first time)

- [ ] **Step 2: Run container locally (smoke test)**

Run:
```bash
# Create a temp data directory with your existing DB
mkdir -p /tmp/rare-books-test-data/index
mkdir -p /tmp/rare-books-test-data/chat
mkdir -p /tmp/rare-books-test-data/auth
cp data/index/bibliographic.db /tmp/rare-books-test-data/index/

# Create temp self-signed cert for local test
openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
    -keyout /tmp/rare-books-test-key.pem \
    -out /tmp/rare-books-test-cert.pem \
    -subj "/CN=localhost"

# Run the container
docker run -d --name rare-books-test \
    -e JWT_SECRET=test-secret-that-is-at-least-32-characters-long \
    -e CORS_ORIGIN=https://localhost \
    -e HTTPS=true \
    -e SESSIONS_DB_PATH=/app/data/chat/sessions.db \
    -e BIBLIOGRAPHIC_DB_PATH=/app/data/index/bibliographic.db \
    -v /tmp/rare-books-test-data:/app/data \
    -v /tmp/rare-books-test-cert.pem:/etc/ssl/certs/rare-books/cert.pem:ro \
    -v /tmp/rare-books-test-key.pem:/etc/ssl/certs/rare-books/key.pem:ro \
    -p 8080:80 -p 8443:443 \
    rare-books:test
```

- [ ] **Step 3: Verify health check**

Run: `sleep 10 && curl -fk https://localhost:8443/health`
Expected: `{"status": "healthy", "database_connected": true, ...}`

- [ ] **Step 4: Verify frontend is served**

Run: `curl -fk https://localhost:8443/ | head -5`
Expected: HTML starting with `<!DOCTYPE html>` (the React SPA)

- [ ] **Step 5: Check logs for errors**

Run: `docker logs rare-books-test --tail 30`
Expected: nginx and uvicorn startup messages, no errors

- [ ] **Step 6: Cleanup**

Run:
```bash
docker stop rare-books-test && docker rm rare-books-test
rm -rf /tmp/rare-books-test-data /tmp/rare-books-test-cert.pem /tmp/rare-books-test-key.pem
```

- [ ] **Step 7: Commit the spec and plan docs**

```bash
git add docs/superpowers/specs/2026-03-29-docker-deployment-design.md
git add docs/superpowers/plans/2026-03-29-docker-deployment.md
git commit -m "$(cat <<'EOF'
docs: add Docker deployment design spec and implementation plan

Design spec covers architecture decisions, environment variables,
deploy workflow, SSL setup, cost control, and AWS migration skeleton.
Implementation plan has 9 tasks with pre-requirements checklist.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: First Deploy to Oracle A1

**Pre-condition:** All pre-requirements from the top of this plan are completed. deploy.sh has been configured with the correct `SERVER_USER`, `SERVER_HOST`, `SSH_KEY`, `SSL_CERT_FILE`, and `SSL_KEY_FILE` values.

- [ ] **Step 1: Ensure data directory exists on server**

Run:
```bash
SSH_CMD="ssh -i <your-key> <user>@<host>"
$SSH_CMD "mkdir -p ~/rare-books-data/index ~/rare-books-data/chat ~/rare-books-data/auth ~/rare-books-data/normalization"
```

- [ ] **Step 2: Copy initial data files to server**

Run:
```bash
# Copy the bibliographic database
scp -i <your-key> data/index/bibliographic.db <user>@<host>:~/rare-books-data/index/

# Copy normalization alias maps (needed at runtime)
scp -i <your-key> data/normalization/place_aliases/place_alias_map.json <user>@<host>:~/rare-books-data/normalization/place_aliases/
scp -i <your-key> -r data/normalization/publisher_aliases/ <user>@<host>:~/rare-books-data/normalization/
scp -i <your-key> data/normalization/marc_country_codes.json <user>@<host>:~/rare-books-data/normalization/
scp -i <your-key> data/normalization/place_geocodes.json <user>@<host>:~/rare-books-data/normalization/

# Copy enrichment cache if it exists
scp -i <your-key> data/enrichment/cache.db <user>@<host>:~/rare-books-data/enrichment/ 2>/dev/null || true
```

- [ ] **Step 3: Verify env file exists on server**

Run: `$SSH_CMD "cat ~/rare-books.env | head -3"`
Expected: Shows first 3 lines of your env file (with OPENAI_API_KEY, etc.)

- [ ] **Step 4: Verify SSL certs exist on server**

Run: `$SSH_CMD "ls -la ~/rare-books-certs/"`
Expected: Shows your .crt/.pem and .key files

- [ ] **Step 5: Deploy**

Run: `./deploy.sh`
Expected:
- rsync syncs source code
- docker build completes on server
- container starts
- health check passes
- Prints: `Site live at: https://cenlib-rare-books.nurdillo.com`

- [ ] **Step 6: Verify in browser**

Open: `https://cenlib-rare-books.nurdillo.com`
Expected: React frontend loads, login page appears

- [ ] **Step 7: Test login with admin credentials**

Log in with the ADMIN_EMAIL / ADMIN_PASSWORD from your env file.
Expected: Successful login, can access the app.

- [ ] **Step 8: Test a query**

Try a search query like "books published in Paris"
Expected: Results appear with evidence from MARC fields.
