#!/bin/bash
#
# Run the Streamlit Chat UI for Rare Books Discovery
#
# Usage: ./run_chat_ui.sh [--port PORT]
#
# This script automatically:
#   - Starts the API server (if not running)
#   - Starts the Streamlit UI
#   - Cleans up on exit
#
# Prerequisites:
#   - Poetry dependencies installed (poetry install)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

API_PORT=8000
UI_PORT="${1:-8501}"
if [[ "$1" == "--port" ]]; then
    UI_PORT="${2:-8501}"
fi

API_PID=""

# Cleanup function to kill API server on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    if [[ -n "$API_PID" ]]; then
        echo "Stopping API server (PID: $API_PID)..."
        kill "$API_PID" 2>/dev/null || true
    fi
    # Kill any existing Streamlit processes for this app
    STREAMLIT_PIDS=$(pgrep -f "streamlit run app/ui_chat/main.py" 2>/dev/null || true)
    if [[ -n "$STREAMLIT_PIDS" ]]; then
        echo "$STREAMLIT_PIDS" | xargs kill 2>/dev/null || true
    fi
    echo "Done."
}

trap cleanup EXIT INT TERM

echo "=========================================="
echo "  Rare Books Discovery - Chat UI"
echo "=========================================="
echo ""

# Kill any existing API server on port 8000
echo "Checking for existing API server..."
EXISTING_API_PIDS=$(lsof -ti:$API_PORT 2>/dev/null || true)
if [[ -n "$EXISTING_API_PIDS" ]]; then
    echo "Stopping existing API server on port $API_PORT..."
    echo "$EXISTING_API_PIDS" | xargs kill 2>/dev/null || true
    sleep 1
fi

# Kill any existing Streamlit processes for this app
echo "Checking for existing Streamlit instances..."
EXISTING_UI_PIDS=$(pgrep -f "streamlit run app/ui_chat/main.py" 2>/dev/null || true)
if [[ -n "$EXISTING_UI_PIDS" ]]; then
    echo "Stopping existing Streamlit instances..."
    echo "$EXISTING_UI_PIDS" | xargs kill 2>/dev/null || true
    sleep 1
fi

# Start API server in background
echo "Starting API server on port $API_PORT..."
poetry run uvicorn app.api.main:app --port $API_PORT &
API_PID=$!

# Wait for API server to be ready
echo "Waiting for API server to start..."
for i in {1..30}; do
    if curl -s "http://localhost:$API_PORT/health" > /dev/null 2>&1; then
        echo "API server ready!"
        break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "ERROR: API server failed to start"
        exit 1
    fi
    sleep 0.5
done

echo ""
echo "Starting Streamlit UI on port $UI_PORT..."
echo ""
echo "=========================================="
echo "  API:  http://localhost:$API_PORT"
echo "  UI:   http://localhost:$UI_PORT"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

poetry run streamlit run app/ui_chat/main.py \
    --server.port "$UI_PORT" \
    --server.headless true \
    --browser.gatherUsageStats false
