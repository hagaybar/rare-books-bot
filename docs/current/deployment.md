# Deployment
> Last verified: 2026-04-01
> Source of truth for: Production deployment infrastructure, Docker configuration, deploy commands, server setup, SSL, nginx, and troubleshooting

## Production Environment

| Property | Value |
|----------|-------|
| **Domain** | `https://cenlib-rare-books.nurdillo.com` |
| **Server** | `151.145.90.19` (Ubuntu 22.04, ARM64) |
| **Stack** | Docker container (Python 3.12 + Node 20 multi-stage build) behind host nginx reverse proxy |
| **SSH access** | `ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19` |

---

## Architecture

```
Client (HTTPS)
  |
  v
Host nginx (port 443, SSL termination)
  |
  v (proxy_pass)
Docker container (port 8001 -> uvicorn :8000)
  |
  v
FastAPI (API + React SPA static files)
  |
  v
SQLite databases (Docker volume /app/data)
```

- **Host nginx** handles SSL termination and proxies to the Docker container
- **Docker container** runs uvicorn serving both the FastAPI API and React SPA static files
- **Data persistence** via a Docker volume mounted at `/app/data`
- **No nginx inside Docker** -- the host nginx handles all routing

---

## Infrastructure Details

| Component | Details |
|-----------|---------|
| Container | `rare-books` on port 8001, proxied by host nginx |
| Data volume | `~/rare-books-data` mounted to `/app/data` (SQLite DBs, logs) |
| Env file | `~/rare-books.env` (OPENAI_API_KEY, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD) |
| Deploy script | `./deploy.sh` at repo root |
| Dockerfile | Multi-stage: Node 20 builds frontend, Python 3.12 runs API (2 uvicorn workers) |
| Nginx configs | `docker/cenlib-rare-books.conf` (host), `docker/nginx.conf` (reference) |
| Entrypoint | `docker/entrypoint.sh` (creates data dirs, seeds admin user on first run) |

### Docker Container Contents

- **Python 3.12** with Poetry-managed dependencies (production only)
- **uvicorn** serving FastAPI on port 8000 (2 workers)
- **React SPA** built during Docker build, served by FastAPI as static files
- **Entrypoint script** creates data directories and seeds admin user on first run

### Data Volume (`~/rare-books-data` -> `/app/data`)

Persisted data:
- `index/bibliographic.db` -- main bibliographic database
- `chat/sessions.db` -- conversation sessions
- `auth/auth.db` -- user authentication
- `qa/qa.db` -- QA labels and gold sets
- Normalization maps, enrichment data, metadata

---

## Deploy Commands

All commands run from the project root on your local machine.

### Code-Only Deploy (most common)

```bash
./deploy.sh
```

1. Rsync source code to server
2. Docker build (multi-stage: Node frontend + Python backend)
3. Restart container
4. Run health check

### Code + Database Deploy

```bash
./deploy.sh --update-db
```

Same as above, plus copies local `bibliographic.db` to the server.

### Database-Only Update

```bash
./deploy.sh --db-only
```

Copies a fresh `bibliographic.db` without rebuilding the container. Restart the container manually afterward:

```bash
ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "docker restart rare-books"
```

### Rollback

```bash
./deploy.sh --rollback
```

Restarts the container with the previous Docker image tag.

---

## Post-Deploy Checks

```bash
# Health check
ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "curl -sf http://127.0.0.1:8000/health"

# View logs
ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "docker logs rare-books --tail 50"

# Restart without rebuild
ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "docker restart rare-books"

# Check container status
ssh -i ~/.ssh/rarebooks_a1 rarebooks@151.145.90.19 "docker ps"
```

---

## Server Setup (First Time)

### 1. Create Dedicated User

Using admin account on the server:

```bash
sudo useradd -m -s /bin/bash rarebooks
sudo usermod -aG docker rarebooks
```

### 2. SSH Key Authentication

On local machine:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/rarebooks_key -C "rarebooks@server"
```

On server (as admin):
```bash
sudo mkdir -p /home/rarebooks/.ssh
# Copy public key into authorized_keys
sudo nano /home/rarebooks/.ssh/authorized_keys
sudo chown -R rarebooks:rarebooks /home/rarebooks/.ssh
sudo chmod 700 /home/rarebooks/.ssh
sudo chmod 600 /home/rarebooks/.ssh/authorized_keys
```

### 3. Create Project Directories

As `rarebooks` user:
```bash
mkdir -p ~/rare-books-bot ~/rare-books-data ~/rare-books-certs
```

### 4. Copy SSL Certificates

As admin:
```bash
sudo cp /path/to/your/fullchain.pem /home/rarebooks/rare-books-certs/
sudo cp /path/to/your/private_key.key /home/rarebooks/rare-books-certs/
sudo chown -R rarebooks:rarebooks /home/rarebooks/rare-books-certs
sudo chmod 600 /home/rarebooks/rare-books-certs/*
```

### 5. Create Environment File

As `rarebooks`:
```bash
nano ~/rare-books.env
```

Contents:
```
OPENAI_API_KEY=<your-openai-api-key>
JWT_SECRET=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
CORS_ORIGIN=https://<your-subdomain>
HTTPS=true
SESSIONS_DB_PATH=/app/data/chat/sessions.db
BIBLIOGRAPHIC_DB_PATH=/app/data/index/bibliographic.db
ADMIN_EMAIL=<admin-username>
ADMIN_PASSWORD=<admin-password-min-8-chars>
```

Lock permissions:
```bash
chmod 600 ~/rare-books.env
```

### 6. Configure Host nginx

Create a site config (as admin):
```bash
sudo nano /etc/nginx/sites-available/your-subdomain
```

Use `docker/cenlib-rare-books.conf` as a template. Key points:
- Update `server_name` to your subdomain
- Update `ssl_certificate` and `ssl_certificate_key` paths
- `proxy_pass` points to `http://127.0.0.1:8001`
- WebSocket headers (`Upgrade`, `Connection`) are included

Enable and reload:
```bash
sudo ln -s /etc/nginx/sites-available/your-subdomain /etc/nginx/sites-enabled/
sudo nginx -t
sudo nginx -s reload
```

---

## Configuration

Before first deploy, edit `deploy.sh` and set:

```bash
SERVER_USER="rarebooks"           # SSH username
SERVER_HOST="<server-ip>"         # Server IP address
SSH_KEY="~/.ssh/rarebooks_key"    # Path to SSH private key
HOST_PORT=8001                    # Port exposed to host nginx
```

---

## Prerequisites

### Local Machine
1. Docker Desktop with buildx support (`docker buildx version`)
2. SSH key access to the server

### Server
1. Docker installed, deploy user in `docker` group
2. nginx running with SSL certificate for subdomain
3. DNS A record pointing subdomain to server IP
4. Firewall allowing inbound ports 80 and 443

---

## Troubleshooting

### Container won't start

Check logs: `docker logs rare-books --tail 100`

Common issues:
- Missing environment variables in `~/rare-books.env`
- Port 8001 already in use (`ss -tlnp | grep 8001`)
- Missing data volume directory

### 502 Bad Gateway

- Container may not be running: `docker ps`
- Check if uvicorn started: `docker logs rare-books --tail 20`
- Verify host nginx config points to correct port

### SSL errors

- Verify cert files exist and are readable by the deploy user
- Check cert covers your subdomain: `openssl x509 -in cert.pem -text -noout | grep -A1 "Subject Alternative Name"`
- Ensure host nginx config has correct cert paths

### Health check fails after deploy

- Wait 10-15 seconds for uvicorn to start (2 workers)
- Check if `bibliographic.db` exists in the data volume
- Verify `OPENAI_API_KEY` is set in the env file
