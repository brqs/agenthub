#!/usr/bin/env bash
set -Eeuo pipefail

PACKAGE_DIR="${1:-mac-codex-package}"
RESTORE_DB=0
RESET_VOLUMES=0
SKIP_FRONTEND=0
FORCE_REBUILD=0

shift || true
for arg in "$@"; do
  case "$arg" in
    --restore-db)
      RESTORE_DB=1
      ;;
    --reset-volumes)
      RESET_VOLUMES=1
      ;;
    --skip-frontend)
      SKIP_FRONTEND=1
      ;;
    --rebuild)
      FORCE_REBUILD=1
      ;;
    --help|-h)
      cat <<'EOF'
Import an AgentHub Mac Codex package.

Usage:
  ./scripts/import-agenthub-mac-codex-package.sh <package-dir> [options]

Options:
  --restore-db     Restore package agenthub.sql into Postgres.
  --reset-volumes  Run docker compose down -v before import. Destructive.
  --skip-frontend  Do not start frontend after import.
  --rebuild        Ignore imported backend image and rebuild on this Mac.
EOF
      exit 0
      ;;
    *)
      echo "[AgentHub] Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PACKAGE_DIR="$(cd "${PACKAGE_DIR}" && pwd)"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
FRONTEND_LOG="${PROJECT_ROOT}/.agenthub-mac-frontend.log"
FRONTEND_PID_FILE="${PROJECT_ROOT}/.agenthub-mac-frontend.pid"

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

compose_base=(docker compose)
compose_with_image=(docker compose -f docker-compose.yml -f docker-compose.mac-image.yml)

port_has_listener() {
  local port="$1"
  lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_frontend_deps() {
  require_command node
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
  if command -v open >/dev/null 2>&1; then
    open "${FRONTEND_URL}" >/dev/null 2>&1 || true
  fi
}

main() {
  cd "${PROJECT_ROOT}"
  require_command docker
  require_command curl
  require_command tar

  if [ ! -d "${PACKAGE_DIR}" ]; then
    echo "[AgentHub] Package directory not found: ${PACKAGE_DIR}" >&2
    exit 1
  fi

  log "Project: ${PROJECT_ROOT}"
  log "Package: ${PACKAGE_DIR}"

  if [ ! -f ".env" ]; then
    if [ -f "${PACKAGE_DIR}/.env" ]; then
      log "Copying packaged .env into project root."
      cp "${PACKAGE_DIR}/.env" .env
    else
      log "No .env found; copying .env.example."
      cp .env.example .env
    fi
  fi

  if [ "$RESET_VOLUMES" -eq 1 ]; then
    log "Resetting Docker volumes. This deletes local Mac AgentHub data."
    docker compose down -v
  fi

  local use_imported_image=0
  if [ "$FORCE_REBUILD" -eq 0 ] && [ -f "${PACKAGE_DIR}/agenthub-backend-linux-amd64.tar" ]; then
    log "Loading packaged backend image..."
    docker load -i "${PACKAGE_DIR}/agenthub-backend-linux-amd64.tar"
    use_imported_image=1
  fi
  local compose_cmd
  if [ "$use_imported_image" -eq 1 ]; then
    compose_cmd=("${compose_with_image[@]}")
  else
    compose_cmd=("${compose_base[@]}")
  fi

  if [ -f "${PACKAGE_DIR}/workspaces.tgz" ]; then
    log "Restoring workspaces archive..."
    rm -rf workspaces
    tar xzf "${PACKAGE_DIR}/workspaces.tgz"
  else
    mkdir -p workspaces
  fi

  if [ "$use_imported_image" -eq 1 ]; then
    log "Starting Docker stack with imported backend image..."
    "${compose_cmd[@]}" up -d --no-build postgres redis backend
  else
    log "Starting Docker stack with local backend build..."
    "${compose_cmd[@]}" up -d --build postgres redis backend
  fi

  if [ -f "${PACKAGE_DIR}/uploads-data.tgz" ]; then
    log "Restoring uploads-data volume..."
    "${compose_cmd[@]}" run --rm -T \
      -v "${PACKAGE_DIR}:/import" \
      backend \
      sh -lc 'mkdir -p /app/data/uploads && tar xzf /import/uploads-data.tgz -C /app/data/uploads'
  fi

  if [ -f "${PACKAGE_DIR}/claude-state.tgz" ]; then
    log "Restoring Claude state volume..."
    "${compose_cmd[@]}" run --rm -T \
      -v "${PACKAGE_DIR}:/import" \
      backend \
      sh -lc 'mkdir -p "$AGENTHUB_CLAUDE_AUTH_DIR" && tar xzf /import/claude-state.tgz -C "$AGENTHUB_CLAUDE_AUTH_DIR"'
  fi

  if [ -f "${PACKAGE_DIR}/opencode-state.tgz" ]; then
    log "Restoring OpenCode state volume..."
    "${compose_cmd[@]}" run --rm -T \
      -v "${PACKAGE_DIR}:/import" \
      backend \
      sh -lc 'mkdir -p "$AGENTHUB_OPENCODE_AUTH_DIR" && tar xzf /import/opencode-state.tgz -C "$AGENTHUB_OPENCODE_AUTH_DIR"'
  fi

  if [ "$RESTORE_DB" -eq 1 ] && [ -f "${PACKAGE_DIR}/agenthub.sql" ]; then
    log "Restoring database dump..."
    cat "${PACKAGE_DIR}/agenthub.sql" | "${compose_cmd[@]}" exec -T postgres psql -U "${POSTGRES_USER:-agenthub}" -d "${POSTGRES_DB:-agenthub}"
  elif [ -f "${PACKAGE_DIR}/agenthub.sql" ]; then
    log "Database dump exists but --restore-db was not passed; skipping DB restore."
  fi

  log "Running migrations..."
  "${compose_cmd[@]}" exec -T backend alembic upgrade head

  log "Seeding built-in agents..."
  "${compose_cmd[@]}" exec -T backend python -m app.seeds.seed_agents

  wait_for_url "${BACKEND_URL}/health" "Backend health check" 120

  if [ "$SKIP_FRONTEND" -eq 0 ]; then
    start_frontend
  else
    log "Skipping frontend startup."
  fi

  log "Import complete."
}

main "$@"
