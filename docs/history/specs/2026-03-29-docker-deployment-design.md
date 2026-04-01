# Docker Deployment Design

## Goal

Deploy the rare-books-bot application to an Oracle Ampere A1 test server (4 OCPU / 24GB RAM, ARM64) for a small group of 5-20 known users at `https://cenlib-rare-books.nurdillo.com`.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Container topology | Single container (nginx + FastAPI) | Simplest for test phase; split for AWS later |
| Registry | None — build on server | No accounts/auth; Dockerfile stays portable |
| Deploy method | Semi-automated script (`deploy.sh`) | One command from laptop, no CI/CD overhead |
| DB storage | Docker volume, mounted at `/app/data` | Survives container rebuilds; DB never in image |
| SSL | Existing certificate files (.crt + .key) | Already purchased with domain |
| Cost control | Per-user rate limit + global monthly budget | Two layers: existing slowapi + existing `monthly_cost_cap_usd` in auth.db |

## Architecture

```
 +------------------------------------------------------+
 |  Docker Container: rare-books                        |
 |                                                      |
 |  +----------------------------------------------+   |
 |  |  nginx (:443 HTTPS, :80 -> redirect)          |   |
 |  |                                               |   |
 |  |  /           -> React static build            |   |
 |  |  /chat       -> FastAPI :8000 (POST)          |   |
 |  |  /auth       -> FastAPI :8000                 |   |
 |  |  /metadata   -> FastAPI :8000                 |   |
 |  |  /health     -> FastAPI :8000                 |   |
 |  |  /ws         -> FastAPI :8000 (WebSocket)     |   |
 |  |  /diagnostics -> FastAPI :8000                |   |
 |  |  /network/*  -> FastAPI :8000 (sub-routes)    |   |
 |  |  /sessions   -> FastAPI :8000                 |   |
 |  +----------------------------------------------+   |
 |                                                      |
 |  +----------------------------------------------+   |
 |  |  FastAPI + Uvicorn :8000 (internal only)      |   |
 |  |  Python 3.12 / Poetry                         |   |
 |  +----------------------------------------------+   |
 |                                                      |
 |  supervisord manages nginx + uvicorn                 |
 +------------------------+-----------------------------+
                          | mount
             +------------v------------------+
             |  Docker Volume: rare-books-data  |
             |  Mounted at /app/data -- all of: |
             |  index/bibliographic.db          |
             |  chat/sessions.db               |
             |  auth/auth.db                   |
             |  qa/qa.db                       |
             |  normalization/                 |
             |  enrichment/                    |
             |  metadata/                      |
             |  query_plan_cache.jsonl         |
             +----------------------------------+
```

**DNS**: `cenlib-rare-books.nurdillo.com` -> A record -> Oracle A1 public IP

## Environment Variables

Stored in `~/rare-books.env` on the server (never in the image):

```
OPENAI_API_KEY=sk-...
JWT_SECRET=<random-64-char>
CORS_ORIGIN=https://cenlib-rare-books.nurdillo.com
HTTPS=true
SESSIONS_DB_PATH=/app/data/chat/sessions.db
BIBLIOGRAPHIC_DB_PATH=/app/data/index/bibliographic.db
```

## Deploy Workflow

`deploy.sh` runs from the developer's laptop:

1. **rsync** source code to server (excludes: node_modules, __pycache__, .git, .env, data/)
2. **scp** bibliographic.db to the data volume on server (only with `--update-db` flag)
3. **ssh** into server: `docker build` -> stop old container -> start new container with tagged image
4. **health check**: curl `/health` endpoint (retries 3x with 5s delay)

### Deploy commands

```bash
./deploy.sh                  # code only -- fast deploy
./deploy.sh --update-db      # code + fresh bibliographic.db (only bibliographic.db, not auth/sessions)
./deploy.sh --db-only        # just update bibliographic.db, no rebuild
./deploy.sh --rollback       # restart previous tagged image
```

### Image tagging and rollback

Each build tags the image as `rare-books:<git-short-sha>` and `rare-books:latest`. The deploy script records the previous image tag before replacing it. `--rollback` restarts the container with the previous tag. Keep at least 2 images on the server.

## Cost Control

### Layer 1: Per-User Rate Limit (existing)

Already implemented via `slowapi`: 10 req/min per IP on `/chat`. Returns 429 when exceeded. No changes needed.

### Layer 2: Global Monthly Budget (existing -- configure for production)

The codebase already has token tracking and a monthly cost cap:
- `app/api/security.py`: `record_token_usage()` and `check_quota()` write to `token_usage` table in `auth.db`
- `app/api/auth_db.py`: `monthly_cost_cap_usd` in the `settings` table (default: 50)

For deployment, set `MONTHLY_BUDGET_USD=10` (or adjust via the admin settings UI). No new code needed -- just configure the existing cap. When the monthly total exceeds the cap, LLM queries return a friendly "budget exceeded" message.

## SSL

Existing certificate files (purchased with domain). Stored on the server at `~/rare-books-certs/` and mounted into the container.

**Setup**:
1. Copy `.crt` and `.key` files to `~/rare-books-certs/` on the server
2. Docker mounts this directory read-only at `/etc/ssl/certs/rare-books/` inside the container
3. nginx.conf references the cert and key from that path
4. Point DNS `cenlib-rare-books.nurdillo.com` -> server public IP

**Renewal**: When the certificate expires, replace the files in `~/rare-books-certs/` and reload nginx: `docker exec rare-books nginx -s reload`.

## New Files

```
rare-books-bot/
  Dockerfile              # Multi-stage: node build + python runtime
  .dockerignore           # Exclude dev files from build context
  deploy.sh               # Semi-automated deploy script
  docker/
    nginx.conf            # SSL + reverse proxy + static + WebSocket upgrade headers
    supervisord.conf      # Process manager for nginx + uvicorn
    entrypoint.sh         # Container startup: seed admin user on first run
```

No new Python modules needed -- cost control already exists in `auth.db`.

## Dockerfile Strategy

Multi-stage build:
1. **Stage 1 (node)**: Install npm deps, build React frontend (`npm run build`)
2. **Stage 2 (python)**: Install Poetry deps, copy app code + frontend dist, install supervisord + nginx

Base image: `python:3.12-slim` (ARM64-native on the A1 server).

`WORKDIR` is set to `/app` (project root) so that all relative `data/` paths in the codebase resolve correctly to the mounted volume at `/app/data`.

## nginx Notes

- WebSocket proxy for `/ws` requires upgrade headers: `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` plus appropriate read/send timeouts.
- All API routes proxy to `http://127.0.0.1:8000` (uvicorn, internal only).
- Static React build served from `/app/frontend/dist`.

## First Deploy -- Admin User Seeding

On first run, `entrypoint.sh` checks if `auth.db` has any admin users. If not, it creates a default admin account using credentials from environment variables (`ADMIN_EMAIL`, `ADMIN_PASSWORD` in `~/rare-books.env`). This ensures at least one user can log in to manage the system.

## Logging

supervisord routes both nginx and uvicorn logs to stdout/stderr, making them accessible via `docker logs rare-books`. No log files on the volume -- keeps things simple for a test deployment.

## Stage 2 -- AWS Migration (Skeleton)

When moving to AWS: split into separate frontend/backend containers, push to a registry (GHCR or ECR), deploy via ECS Fargate or EC2. SQLite may need to migrate to RDS/PostgreSQL if concurrent write access becomes a requirement. The Dockerfile and application code remain unchanged -- the migration is infrastructure-level. Design details deferred until needed.
