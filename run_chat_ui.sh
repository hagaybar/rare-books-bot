#!/bin/bash
#
# Run the Streamlit Chat UI for Rare Books Discovery
#
# Usage: ./run_chat_ui.sh [--port PORT]
#
# Prerequisites:
#   - Poetry dependencies installed (poetry install)
#   - API server running (uvicorn app.api.main:app --reload)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-8501}"
if [[ "$1" == "--port" ]]; then
    PORT="${2:-8501}"
fi

echo "=========================================="
echo "  Rare Books Discovery - Chat UI"
echo "=========================================="
echo ""

# Kill any existing Streamlit processes for this app
echo "Checking for existing Streamlit instances..."
EXISTING_PIDS=$(pgrep -f "streamlit run app/ui_chat/main.py" 2>/dev/null || true)
if [[ -n "$EXISTING_PIDS" ]]; then
    echo "Stopping existing instances: $EXISTING_PIDS"
    echo "$EXISTING_PIDS" | xargs kill 2>/dev/null || true
    sleep 1
fi

echo "Starting Streamlit on port $PORT..."
echo "API endpoint: http://localhost:8000"
echo ""
echo "Make sure the API server is running:"
echo "  uvicorn app.api.main:app --reload"
echo ""
echo "=========================================="
echo ""

poetry run streamlit run app/ui_chat/main.py \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false
