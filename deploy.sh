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
