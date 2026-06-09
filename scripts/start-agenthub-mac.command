#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_LOG="${PROJECT_ROOT}/.agenthub-mac-frontend.log"
FRONTEND_PID_FILE="${PROJECT_ROOT}/.agenthub-mac-frontend.pid"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"

REBUILD=0
SKIP_FRONTEND=0

for arg in "$@"; do
  case "$arg" in
    --rebuild)
      REBUILD=1
      ;;
    --skip-frontend)
      SKIP_FRONTEND=1
      ;;
    --help|-h)
      cat <<'EOF'
AgentHub macOS local starter

Usage:
  ./scripts/start-agenthub-mac.command [--rebuild] [--skip-frontend]

Options:
  --rebuild        Rebuild the backend Docker image before starting.
  --skip-frontend  Start only Docker services and backend migrations/seeds.
EOF
      exit 0
      ;;
    *)
      echo "[AgentHub] Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

log() {
  printf '[AgentHub] %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[AgentHub] Missing required command: $1" >&2
    return 1
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local max_seconds="$3"
  local elapsed=0

  while [ "$elapsed" -lt "$max_seconds" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$label is ready: $url"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "[AgentHub] Timed out waiting for $label at $url" >&2
  return 1
}

port_has_listener() {
  local port="$1"
  lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_frontend_deps() {
  if ! command -v pnpm >/dev/null 2>&1; then
    if command -v corepack >/dev/null 2>&1; then
      log "pnpm not found; enabling Corepack..."
      corepack enable
      corepack prepare pnpm@latest --activate
    else
      echo "[AgentHub] pnpm is missing and corepack is unavailable. Install pnpm first." >&2
      return 1
    fi
  fi

  if [ ! -d "${PROJECT_ROOT}/frontend/node_modules" ]; then
    log "Installing frontend dependencies..."
    (cd "${PROJECT_ROOT}/frontend" && pnpm install)
  fi
}

start_frontend() {
  if [ "$SKIP_FRONTEND" -eq 1 ]; then
    log "Skipping frontend startup by request."
    return 0
  fi

  require_command node
  require_command lsof
  ensure_frontend_deps

  if port_has_listener 5173; then
    log "Frontend port 5173 already has a listener; leaving it alone."
    return 0
  fi

  log "Starting frontend dev server..."
  (
    cd "${PROJECT_ROOT}/frontend"
    VITE_DEV_PROXY_TARGET="${BACKEND_URL}" \
      nohup pnpm dev --host 0.0.0.0 >"${FRONTEND_LOG}" 2>&1 &
    echo "$!" >"${FRONTEND_PID_FILE}"
  )

  wait_for_url "${FRONTEND_URL}" "Frontend" 90
}

main() {
  log "Project: ${PROJECT_ROOT}"
  cd "${PROJECT_ROOT}"

  require_command docker
  require_command curl

  if ! docker compose version >/dev/null 2>&1; then
    echo "[AgentHub] Docker Compose plugin is unavailable. Install Docker Desktop for Mac." >&2
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "[AgentHub] Docker is not running. Start Docker Desktop and run this again." >&2
    exit 1
  fi

  if [ ! -f ".env" ]; then
    log "No .env found; copying .env.example to .env."
    cp .env.example .env
    log "Edit .env later if you need provider keys or custom runtime settings."
  fi

  mkdir -p workspaces

  local backend_image
  backend_image="$(docker compose images -q backend 2>/dev/null || true)"
  if [ "$REBUILD" -eq 1 ] || [ -z "$backend_image" ]; then
    log "Building backend image..."
    docker compose build backend
  fi

  log "Starting Postgres, Redis, and Backend..."
  docker compose up -d postgres redis backend

  log "Running database migrations..."
  docker compose exec -T backend alembic upgrade head

  log "Seeding built-in agents..."
  docker compose exec -T backend python -m app.seeds.seed_agents

  wait_for_url "${BACKEND_URL}/health" "Backend health check" 120

  start_frontend

  log "AgentHub is ready."
  log "Frontend: ${FRONTEND_URL}"
  log "Backend docs: ${BACKEND_URL}/docs"
  log "Frontend log: ${FRONTEND_LOG}"

  if command -v open >/dev/null 2>&1; then
    open "${FRONTEND_URL}" >/dev/null 2>&1 || true
  fi
}

main "$@"
