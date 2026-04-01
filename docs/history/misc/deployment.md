# Docker Deployment Guide

Deploy the rare-books-bot (FastAPI + React) to a Linux server using Docker, behind an existing host nginx reverse proxy.

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
- **No nginx inside Docker** — the host nginx handles all routing

## Prerequisites

### On Your Local Machine
1. Docker Desktop with buildx support (`docker buildx version`)
2. SSH key access to the server (for the deploy user)

### On the Server
1. **Docker** installed and the deploy user added to the `docker` group
2. **nginx** running with access to a wildcard or subdomain SSL certificate
3. **DNS A record** pointing your subdomain to the server's public IP
4. **Firewall** allowing inbound ports 80 and 443

## Server Setup

### 1. Create a Dedicated User

Using your admin account on the server:

```bash
sudo useradd -m -s /bin/bash rarebooks
sudo usermod -aG docker rarebooks
```

### 2. Set Up SSH Key Authentication

On your local machine:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/rarebooks_key -C "rarebooks@server"
```

On the server (as admin):
```bash
sudo mkdir -p /home/rarebooks/.ssh
# Copy your public key content into authorized_keys:
sudo nano /home/rarebooks/.ssh/authorized_keys
sudo chown -R rarebooks:rarebooks /home/rarebooks/.ssh
sudo chmod 700 /home/rarebooks/.ssh
sudo chmod 600 /home/rarebooks/.ssh/authorized_keys
```

Verify: `ssh -i ~/.ssh/rarebooks_key rarebooks@<SERVER_IP>`

### 3. Create Project Directories

As the `rarebooks` user:
```bash
mkdir -p ~/rare-books-bot ~/rare-books-data ~/rare-books-certs
```

### 4. Copy SSL Certificates

As admin, copy your SSL cert and key to the deploy user's cert directory:
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

Lock it down:
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

## Configuration

Before first deploy, edit `deploy.sh` and set:

```bash
SERVER_USER="rarebooks"           # SSH username
SERVER_HOST="<server-ip>"         # Server IP address
SSH_KEY="~/.ssh/rarebooks_key"    # Path to SSH private key
HOST_PORT=8001                    # Port exposed to host nginx
```

Also verify the domain in `deploy.sh` matches your subdomain.

## Deploy Commands

All commands run from the project root on your local machine.

### First Deploy (code + database)
```bash
./deploy.sh --update-db
```

This will:
1. Rsync source code to the server
2. Copy `bibliographic.db` to the server
3. Build the Docker image (multi-stage: Node frontend + Python backend)
4. Start the container
5. Run a health check

### Code-Only Deploy
```bash
./deploy.sh
```

Rebuilds and restarts the container without touching the database.

### Database-Only Update
```bash
./deploy.sh --db-only
```

Copies a fresh `bibliographic.db` without rebuilding the container. Restart the container manually to pick up the new DB:
```bash
ssh -i ~/.ssh/rarebooks_key rarebooks@<SERVER_IP> "docker restart rare-books"
```

### Rollback
```bash
./deploy.sh --rollback
```

Restarts the container with the previous Docker image tag.

## Docker Container Details

### What's Inside
- **Python 3.12** with Poetry-managed dependencies (production only)
- **uvicorn** serving FastAPI on port 8000 (2 workers)
- **React SPA** built during Docker build, served by FastAPI as static files
- **Entrypoint script** that creates data directories and seeds the admin user on first run

### Data Volume
The Docker volume mounted at `/app/data` persists:
- `index/bibliographic.db` — main bibliographic database
- `chat/sessions.db` — conversation sessions
- `auth/auth.db` — user authentication
- `qa/qa.db` — QA labels and gold sets
- Normalization maps, enrichment data, metadata

### Health Check
The container includes a built-in health check:
```bash
curl http://127.0.0.1:8000/health
```

### Viewing Logs
```bash
ssh -i ~/.ssh/rarebooks_key rarebooks@<SERVER_IP> "docker logs rare-books --tail 50"
```

### Restarting
```bash
ssh -i ~/.ssh/rarebooks_key rarebooks@<SERVER_IP> "docker restart rare-books"
```

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
