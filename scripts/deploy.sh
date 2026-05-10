#!/bin/bash

# AIBot2 Deployment Script
# Wraps Docker Compose with environment detection, health checks, and migrations.
#
# Smart deploy: only rebuilds and restarts services whose code changed since
# the last deploy (tracked via .last-deploy commit SHA marker).
#
# Usage:
#   ./scripts/deploy.sh up [--force] [--no-pull] [--no-migrate] [--build-only]
#   ./scripts/deploy.sh down                                Stop all services
#   ./scripts/deploy.sh restart [--force] [service...]      Smart or targeted restart
#   ./scripts/deploy.sh status                              Show service status and health
#   ./scripts/deploy.sh logs [service] [-f] [--tail N]      View logs
#   ./scripts/deploy.sh build                               Build images only
#   ./scripts/deploy.sh migrate                             Run database migrations only
#   ./scripts/deploy.sh shell <service>                     Open a shell in a running container

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Globals ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$PROJECT_ROOT/docker"
cd "$PROJECT_ROOT"

ENV=""           # dev or prod, set by detect_env
COMPOSE_CMD=""   # full docker compose command, set by detect_env
LAST_DEPLOY_FILE="$PROJECT_ROOT/.last-deploy"
AFFECTED_SERVICES=()  # populated by detect_changes
FULL_DEPLOY=false     # set to true when all services need rebuild

# ── Output helpers ──────────────────────────────────────────────────
info()    { echo -e "${BLUE}>>>${NC} $1"; }
ok()      { echo -e "${GREEN} ✓${NC} $1"; }
warn()    { echo -e "${YELLOW} !${NC} $1"; }
err()     { echo -e "${RED} ✗${NC} $1"; }
section() { echo ""; echo -e "${CYAN}${BOLD}─── $1 ───${NC}"; }

# ── .env symlink ───────────────────────────────────────────────────
ensure_env_symlink() {
    if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
        return
    fi

    # Create symlink in docker/ so compose can resolve env vars
    if [[ ! -L "$DOCKER_DIR/.env" ]]; then
        # Remove stale regular file if it exists
        rm -f "$DOCKER_DIR/.env"
        ln -s "$PROJECT_ROOT/.env" "$DOCKER_DIR/.env"
        ok ".env symlinked to docker/"
    fi
}

# ── Environment detection ──────────────────────────────────────────
detect_env() {
    # Allow override: DEPLOY_ENV=prod ./scripts/deploy.sh up
    if [[ -n "${DEPLOY_ENV:-}" ]]; then
        ENV="$DEPLOY_ENV"
    elif [[ -f .env ]] && grep -q 'DEPLOYMENT_MODE=production' .env 2>/dev/null; then
        ENV="prod"
    else
        ENV="dev"
    fi

    # --project-directory keeps build contexts relative to project root
    if [[ "$ENV" == "prod" ]]; then
        COMPOSE_CMD="docker compose -f $DOCKER_DIR/docker-compose.prod.yml --project-directory $PROJECT_ROOT"
    else
        COMPOSE_CMD="docker compose -f $DOCKER_DIR/docker-compose.yml --project-directory $PROJECT_ROOT"
    fi
}

# ── Preflight checks ───────────────────────────────────────────────
preflight() {
    # Docker running?
    if ! docker info >/dev/null 2>&1; then
        err "Docker is not running"
        exit 1
    fi

    # .env exists?
    if [[ ! -f .env ]]; then
        err ".env file not found in project root."
        exit 1
    fi

    # Required vars present?
    local required_vars=(POSTGRES_PASSWORD SECRET_KEY ANTHROPIC_API_KEY)
    local missing=()
    for var in "${required_vars[@]}"; do
        if ! grep -q "^${var}=" .env 2>/dev/null; then
            missing+=("$var")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "Missing required variables in .env: ${missing[*]}"
        exit 1
    fi

    # Prod requires DOMAIN_NAME
    if [[ "$ENV" == "prod" ]]; then
        if ! grep -q "^DOMAIN_NAME=" .env 2>/dev/null; then
            err "Production deploy requires DOMAIN_NAME in .env"
            exit 1
        fi
    fi

    ensure_env_symlink
}

# ── Change detection ───────────────────────────────────────────────
# Maps changed file paths to affected Docker services.
# Sets AFFECTED_SERVICES array and FULL_DEPLOY flag.
detect_changes() {
    if [[ ! -f "$LAST_DEPLOY_FILE" ]]; then
        info "No previous deploy found — full deploy"
        FULL_DEPLOY=true
        return 0
    fi

    local last_sha
    last_sha=$(cat "$LAST_DEPLOY_FILE")

    # Validate the stored SHA still exists in git history
    if ! git rev-parse --verify "$last_sha" >/dev/null 2>&1; then
        warn "Last deploy SHA ($last_sha) not found in git history — full deploy"
        FULL_DEPLOY=true
        return 0
    fi

    local current_sha
    current_sha=$(git rev-parse HEAD)

    if [[ "$last_sha" == "$current_sha" ]]; then
        return 1  # nothing changed
    fi

    local changed_files
    changed_files=$(git diff --name-only "$last_sha".."$current_sha")

    if [[ -z "$changed_files" ]]; then
        return 1  # no file changes (e.g., empty merge)
    fi

    section "Change Detection"
    local commit_count
    commit_count=$(git rev-list --count "$last_sha".."$current_sha")
    info "Last deploy: ${last_sha:0:7} ($commit_count commit(s) ago)"

    # Check for "rebuild everything" triggers
    local needs_all=false
    while IFS= read -r file; do
        case "$file" in
            docker/*|.env)
                needs_all=true
                break
                ;;
        esac
    done <<< "$changed_files"

    if [[ "$needs_all" == true ]]; then
        info "Infrastructure files changed — full rebuild"
        FULL_DEPLOY=true
        echo "$changed_files" | head -10 | while IFS= read -r f; do echo -e "  ${DIM}$f${NC}"; done
        local total
        total=$(echo "$changed_files" | wc -l)
        [[ $total -gt 10 ]] && echo -e "  ${DIM}… and $((total - 10)) more${NC}"
        return 0
    fi

    # Map paths to services
    local -A svc_changed=()
    while IFS= read -r file; do
        case "$file" in
            backend/*)          svc_changed[backend]=1; svc_changed[pipedrive-worker]=1 ;;
            frontend/*)         svc_changed[frontend]=1 ;;
            services/scurry-email/*) svc_changed[scurry-email]=1 ;;
        esac
    done <<< "$changed_files"

    if [[ ${#svc_changed[@]} -eq 0 ]]; then
        info "Changed files don't affect any service (docs, scripts, etc.)"
        return 1  # nothing to deploy
    fi

    AFFECTED_SERVICES=("${!svc_changed[@]}")

    # Print summary
    info "Changed paths:"
    echo "$changed_files" | head -10 | while IFS= read -r f; do echo -e "  ${DIM}$f${NC}"; done
    local total
    total=$(echo "$changed_files" | wc -l)
    [[ $total -gt 10 ]] && echo -e "  ${DIM}… and $((total - 10)) more${NC}"
    echo ""
    ok "Affected services: ${AFFECTED_SERVICES[*]}"

    # Determine what's being skipped
    local all_app_services=(backend frontend scurry-email pipedrive-worker)
    local skipped=()
    for svc in "${all_app_services[@]}"; do
        if [[ -z "${svc_changed[$svc]:-}" ]]; then
            skipped+=("$svc")
        fi
    done
    skipped+=(postgres redis)
    [[ "$ENV" == "prod" ]] && skipped+=(caddy)
    info "Skipping: ${skipped[*]}"

    return 0
}

save_deploy_sha() {
    git rev-parse HEAD > "$LAST_DEPLOY_FILE"
    ok "Deploy SHA saved to .last-deploy"
}

# ── Health check helpers ───────────────────────────────────────────
wait_for_healthy() {
    local container="$1"
    local check_cmd="$2"
    local label="$3"
    local max_attempts="${4:-30}"
    local attempt=1

    while [[ $attempt -le $max_attempts ]]; do
        if eval "$check_cmd" >/dev/null 2>&1; then
            ok "$label is healthy"
            return 0
        fi
        printf "\r  %s waiting… (%d/%d)" "$label" "$attempt" "$max_attempts"
        sleep 2
        ((attempt++))
    done
    echo ""
    err "$label failed to become healthy after $max_attempts attempts"
    return 1
}

check_all_health() {
    local failed=0

    section "Health Checks"

    # Postgres
    if docker exec aibot_postgres pg_isready -U "${POSTGRES_USER:-aibot}" >/dev/null 2>&1; then
        ok "PostgreSQL"
    else
        err "PostgreSQL"; failed=$((failed + 1))
    fi

    # Redis
    if docker exec aibot_redis redis-cli ping >/dev/null 2>&1; then
        ok "Redis"
    else
        err "Redis"; failed=$((failed + 1))
    fi

    # Backend (use python since curl may not be in the image)
    if docker exec aibot_backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')" >/dev/null 2>&1; then
        ok "Backend API"
    else
        if docker exec aibot_backend ps aux 2>/dev/null | grep -q uvicorn; then
            warn "Backend process running but /health not responding"
        else
            err "Backend API"; failed=$((failed + 1))
        fi
    fi

    # Frontend (check via docker network IP)
    local frontend_ip
    frontend_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' aibot_frontend 2>/dev/null)
    if [[ -n "$frontend_ip" ]] && docker exec aibot_backend python -c "import urllib.request; urllib.request.urlopen('http://${frontend_ip}:3000')" >/dev/null 2>&1; then
        ok "Frontend"
    elif docker inspect aibot_frontend --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
        ok "Frontend (container running)"
    else
        err "Frontend"; failed=$((failed + 1))
    fi

    # Scurry email
    if docker exec aibot_scurry_email php -r "file_get_contents('http://localhost/test.php');" >/dev/null 2>&1; then
        ok "Scurry Email Service"
    else
        if docker inspect aibot_scurry_email --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
            ok "Scurry Email Service (container running)"
        else
            warn "Scurry Email Service (may not be configured)"
        fi
    fi

    # Pipedrive worker (container name varies: aibot_pipedrive_worker in prod, auto-named in dev)
    if $COMPOSE_CMD ps pipedrive-worker 2>/dev/null | grep -qiE "running|Up"; then
        ok "Pipedrive Sync Worker"
    else
        # Worker is optional — only warn, don't fail
        warn "Pipedrive Sync Worker (not running)"
    fi

    # Caddy (prod only)
    if [[ "$ENV" == "prod" ]]; then
        if docker exec aibot_caddy caddy version >/dev/null 2>&1; then
            local domain
            domain=$(grep "^DOMAIN_NAME=" .env 2>/dev/null | cut -d= -f2)
            if curl -sf "https://${domain:-localhost}" >/dev/null 2>&1; then
                ok "Caddy (SSL termination)"
            elif curl -sf "http://${domain:-localhost}" >/dev/null 2>&1; then
                warn "Caddy running but SSL not yet provisioned (may take a minute)"
            else
                warn "Caddy running but domain not reachable externally"
            fi
        else
            err "Caddy"; failed=$((failed + 1))
        fi
    fi

    return $failed
}

# ── Subcommand: up ─────────────────────────────────────────────────
cmd_up() {
    local do_migrate=true
    local do_pull=true
    local build_only=false
    local force=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-migrate) do_migrate=false; shift ;;
            --no-pull)    do_pull=false; shift ;;
            --build-only) build_only=true; shift ;;
            --force)      force=true; shift ;;
            *) err "Unknown option: $1"; exit 1 ;;
        esac
    done

    preflight

    section "Deploying ($ENV)"
    local compose_file="docker-compose.yml"
    [[ "$ENV" == "prod" ]] && compose_file="docker-compose.prod.yml"
    info "Compose file: docker/$compose_file"

    # Pull latest code
    if [[ "$do_pull" == true ]]; then
        info "Pulling latest changes…"
        if git pull 2>&1; then
            ok "Code up to date"
        else
            err "git pull failed"
            exit 1
        fi
    fi

    # ── Smart change detection ─────────────────────────────────────
    local smart_deploy=false
    if [[ "$force" == true ]]; then
        info "Force mode — rebuilding everything"
        FULL_DEPLOY=true
    elif detect_changes; then
        # detect_changes sets AFFECTED_SERVICES or FULL_DEPLOY
        smart_deploy=true
    else
        # Return code 1 = nothing changed
        section "Nothing Changed"
        ok "No service-affecting changes since last deploy"
        info "Use --force to rebuild anyway"
        return 0
    fi

    # ── Build ──────────────────────────────────────────────────────
    if [[ "$FULL_DEPLOY" == true ]]; then
        info "Building all images…"
        $COMPOSE_CMD build
        ok "All images built"
    else
        for svc in "${AFFECTED_SERVICES[@]}"; do
            info "Building $svc…"
            $COMPOSE_CMD build "$svc"
            ok "$svc built"
        done
    fi

    if [[ "$build_only" == true ]]; then
        ok "Build-only mode — skipping start"
        return 0
    fi

    # ── Start / Recreate ───────────────────────────────────────────
    if [[ "$FULL_DEPLOY" == true ]]; then
        info "Starting all services…"
        $COMPOSE_CMD up -d
        ok "All containers started"
    else
        # Ensure infrastructure is running first (don't recreate, just start if stopped)
        info "Ensuring infrastructure is running…"
        $COMPOSE_CMD up -d --no-recreate postgres redis
        ok "Infrastructure ready"

        # Recreate only affected services
        for svc in "${AFFECTED_SERVICES[@]}"; do
            info "Recreating $svc…"
            $COMPOSE_CMD up -d --force-recreate "$svc"
            ok "$svc recreated"
        done
    fi

    # ── Health checks ──────────────────────────────────────────────
    section "Waiting for Services"

    # Always check infrastructure health (they should be running)
    wait_for_healthy "aibot_postgres" \
        "docker exec aibot_postgres pg_isready -U \${POSTGRES_USER:-aibot}" \
        "PostgreSQL" 30

    wait_for_healthy "aibot_redis" \
        "docker exec aibot_redis redis-cli ping" \
        "Redis" 15

    # Only check app services that were affected (or all on full deploy)
    local check_backend=false check_frontend=false check_scurry=false

    if [[ "$FULL_DEPLOY" == true ]]; then
        check_backend=true; check_frontend=true; check_scurry=true
    else
        for svc in "${AFFECTED_SERVICES[@]}"; do
            case "$svc" in
                backend)      check_backend=true ;;
                frontend)     check_frontend=true ;;
                scurry-email) check_scurry=true ;;
            esac
        done
        # Backend depends on scurry-email, so if scurry changed check backend too
        [[ "$check_scurry" == true ]] && check_backend=true
    fi

    if [[ "$check_scurry" == true ]]; then
        wait_for_healthy "aibot_scurry_email" \
            "docker inspect aibot_scurry_email --format '{{.State.Health.Status}}' | grep -q healthy" \
            "Scurry Email" 20 || warn "Scurry email didn't pass health check — continuing"
    fi

    if [[ "$check_backend" == true ]]; then
        wait_for_healthy "aibot_backend" \
            "docker exec aibot_backend python -c \"import urllib.request; urllib.request.urlopen('http://localhost:9000/health')\"" \
            "Backend API" 45 || {
                warn "Backend didn't respond to /health yet — checking process"
                if docker inspect aibot_backend --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
                    warn "Container is running; it may still be starting"
                else
                    err "Backend container is not running"
                    info "Check logs: ./scripts/deploy.sh logs backend"
                    exit 1
                fi
            }
    fi

    if [[ "$check_frontend" == true ]]; then
        wait_for_healthy "aibot_frontend" \
            "docker inspect aibot_frontend --format '{{.State.Running}}' | grep -q true" \
            "Frontend" 30
    fi

    # Caddy (prod only, full deploy only)
    if [[ "$ENV" == "prod" && "$FULL_DEPLOY" == true ]]; then
        wait_for_healthy "aibot_caddy" \
            "docker exec aibot_caddy caddy version" \
            "Caddy" 15
    fi

    # Migrate only if backend changed (dev only — prod runs migrate.py on startup)
    if [[ "$do_migrate" == true && "$ENV" == "dev" ]]; then
        if [[ "$FULL_DEPLOY" == true || "$check_backend" == true ]]; then
            section "Database Migrations"
            info "Running migrations…"
            if docker exec aibot_backend python migrate.py; then
                ok "Migrations complete"
            else
                err "Migrations failed"
                info "Check logs: ./scripts/deploy.sh logs backend"
                exit 1
            fi
        else
            info "Skipping migrations (backend unchanged)"
        fi
    fi

    # Save deploy marker
    save_deploy_sha

    # Final verification
    if check_all_health; then
        section "Deploy Complete"
        if [[ "$FULL_DEPLOY" == true ]]; then
            ok "All services rebuilt — $ENV environment"
        else
            ok "Updated: ${AFFECTED_SERVICES[*]} — $ENV environment"
        fi
        echo ""
        if [[ "$ENV" == "prod" ]]; then
            local domain
            domain=$(grep "^DOMAIN_NAME=" .env 2>/dev/null | cut -d= -f2)
            info "Application: https://$domain"
        else
            info "Frontend:  http://localhost:${FRONTEND_PORT:-3000}"
            info "Backend:   http://localhost:9000"
            info "API Docs:  http://localhost:${FRONTEND_PORT:-3000}/api/docs"
        fi
    else
        warn "Some services are unhealthy — check logs"
    fi
}

# ── Subcommand: down ───────────────────────────────────────────────
cmd_down() {
    section "Stopping Services ($ENV)"
    $COMPOSE_CMD down "$@"
    ok "All services stopped"
}

# ── Subcommand: restart ────────────────────────────────────────────
cmd_restart() {
    local services=()
    local force=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force) force=true; shift ;;
            *)       services+=("$1"); shift ;;
        esac
    done

    preflight

    if [[ ${#services[@]} -gt 0 ]]; then
        # Explicit services — restart exactly what was asked
        section "Restarting: ${services[*]} ($ENV)"
        for svc in "${services[@]}"; do
            info "Rebuilding $svc…"
            $COMPOSE_CMD build "$svc"
            info "Restarting $svc…"
            $COMPOSE_CMD up -d --force-recreate "$svc"
            ok "$svc restarted"
        done
    elif [[ "$force" == true ]]; then
        section "Full Restart ($ENV)"
        info "Rebuilding all images…"
        $COMPOSE_CMD build
        ok "Images rebuilt"
        info "Restarting all services…"
        $COMPOSE_CMD up -d --force-recreate
        ok "Services restarted"
    else
        # Smart restart — only changed services
        if detect_changes; then
            if [[ "$FULL_DEPLOY" == true ]]; then
                section "Full Restart ($ENV)"
                info "Infrastructure changes detected — rebuilding all"
                $COMPOSE_CMD build
                ok "Images rebuilt"
                $COMPOSE_CMD up -d --force-recreate
                ok "Services restarted"
            else
                section "Smart Restart: ${AFFECTED_SERVICES[*]} ($ENV)"
                for svc in "${AFFECTED_SERVICES[@]}"; do
                    info "Rebuilding $svc…"
                    $COMPOSE_CMD build "$svc"
                    info "Restarting $svc…"
                    $COMPOSE_CMD up -d --force-recreate "$svc"
                    ok "$svc restarted"
                done
            fi
        else
            section "Nothing Changed"
            ok "No service-affecting changes since last deploy"
            info "Use --force or specify services: ./scripts/deploy.sh restart backend"
            return 0
        fi
    fi

    # Save deploy marker
    save_deploy_sha

    # Quick health check
    sleep 3
    check_all_health || warn "Some services still starting — re-check with: ./scripts/deploy.sh status"
}

# ── Subcommand: status ─────────────────────────────────────────────
cmd_status() {
    section "Service Status ($ENV)"
    $COMPOSE_CMD ps
    check_all_health || true
}

# ── Subcommand: logs ───────────────────────────────────────────────
cmd_logs() {
    local follow=false
    local tail="100"
    local service=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--follow) follow=true; shift ;;
            --tail) tail="$2"; shift 2 ;;
            -*) err "Unknown option: $1"; exit 1 ;;
            *) service="$1"; shift ;;
        esac
    done

    local args=(logs --tail "$tail")
    [[ "$follow" == true ]] && args+=(-f)
    [[ -n "$service" ]] && args+=("$service")

    $COMPOSE_CMD "${args[@]}"
}

# ── Subcommand: build ──────────────────────────────────────────────
cmd_build() {
    preflight

    section "Building Images ($ENV)"
    $COMPOSE_CMD build "$@"
    ok "Build complete"
}

# ── Subcommand: migrate ────────────────────────────────────────────
cmd_migrate() {
    section "Running Migrations"

    if ! docker exec aibot_postgres pg_isready -U "${POSTGRES_USER:-aibot}" >/dev/null 2>&1; then
        err "PostgreSQL is not running. Start services first: ./scripts/deploy.sh up"
        exit 1
    fi

    if docker exec aibot_backend python migrate.py; then
        ok "Migrations complete"
    else
        err "Migrations failed"
        exit 1
    fi
}

# ── Subcommand: shell ──────────────────────────────────────────────
cmd_shell() {
    local service="${1:-backend}"
    local container_map=(
        "backend:aibot_backend"
        "frontend:aibot_frontend"
        "postgres:aibot_postgres"
        "redis:aibot_redis"
        "caddy:aibot_caddy"
        "scurry:aibot_scurry_email"
        "scurry-email:aibot_scurry_email"
        "pipedrive-worker:aibot_pipedrive_worker"
    )

    local container=""
    for entry in "${container_map[@]}"; do
        local key="${entry%%:*}"
        local val="${entry##*:}"
        if [[ "$service" == "$key" ]]; then
            container="$val"
            break
        fi
    done

    if [[ -z "$container" ]]; then
        err "Unknown service: $service"
        info "Available: backend, frontend, postgres, redis, caddy, scurry, pipedrive-worker"
        exit 1
    fi

    local shell_cmd="bash"
    # Alpine images don't have bash
    if [[ "$service" == "postgres" || "$service" == "redis" || "$service" == "caddy" || "$service" == "frontend" ]]; then
        shell_cmd="sh"
    fi

    info "Opening shell in $container…"
    docker exec -it "$container" "$shell_cmd"
}

# ── Usage ───────────────────────────────────────────────────────────
usage() {
    echo -e "${BOLD}AIBot2 Deploy${NC} — Smart Docker Compose wrapper with change detection"
    echo ""
    echo -e "${BOLD}Usage:${NC}"
    echo "  ./scripts/deploy.sh <command> [options]"
    echo ""
    echo -e "${BOLD}Commands:${NC}"
    echo "  up [options]                       Smart deploy — only rebuild changed services"
    echo "     --force                           Override change detection, rebuild everything"
    echo "     --no-pull                         Skip git pull"
    echo "     --no-migrate                      Skip database migrations"
    echo "     --build-only                      Build images without starting"
    echo "  down [docker-compose args]         Stop and remove all containers"
    echo "  restart [--force] [service...]     Smart restart — only changed services"
    echo "                                     Pass service names to override detection"
    echo "  status                             Show container status and run health checks"
    echo "  logs [service] [-f] [--tail N]     View service logs (default: last 100 lines)"
    echo "  build [service...]                 Build images without starting"
    echo "  migrate                            Run database migrations"
    echo "  shell <service>                    Open a shell in a container (backend, frontend,"
    echo "                                     postgres, redis, caddy, scurry)"
    echo ""
    echo -e "${BOLD}Smart Deploy:${NC}"
    echo "  Tracks the last deployed commit in .last-deploy and uses git diff to"
    echo "  determine which services changed. Only rebuilds and restarts affected"
    echo "  services. Infrastructure (postgres, redis) is never restarted unless"
    echo "  docker/ or Dockerfile changes are detected."
    echo ""
    echo -e "${BOLD}  Path mapping:${NC}"
    echo "    backend/**               → backend, pipedrive-worker"
    echo "    frontend/**              → frontend"
    echo "    services/scurry-email/** → scurry-email"
    echo "    docker/** | .env         → all services"
    echo "    Other files              → ignored"
    echo ""
    echo -e "${BOLD}Environment:${NC}"
    echo "  Auto-detected from .env DEPLOYMENT_MODE, or override with:"
    echo "    DEPLOY_ENV=prod ./scripts/deploy.sh up"
    echo ""
    echo "  Dev:  uses docker/docker-compose.yml       (no Caddy, ports exposed)"
    echo "  Prod: uses docker/docker-compose.prod.yml  (Caddy SSL, ports internal)"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  ./scripts/deploy.sh up                     # Smart deploy (only changed services)"
    echo "  ./scripts/deploy.sh up --force             # Full deploy (rebuild everything)"
    echo "  ./scripts/deploy.sh up --no-pull           # Deploy without git pull"
    echo "  ./scripts/deploy.sh restart                # Smart restart (only changed services)"
    echo "  ./scripts/deploy.sh restart backend        # Force restart just the backend"
    echo "  ./scripts/deploy.sh logs backend -f        # Follow backend logs"
    echo "  ./scripts/deploy.sh shell postgres         # Open shell in postgres container"
    echo "  DEPLOY_ENV=prod ./scripts/deploy.sh up     # Force production deploy"
    echo ""
}

# ── Main ────────────────────────────────────────────────────────────
# Source .env for variable substitution (FRONTEND_PORT, POSTGRES_USER, etc.)
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

detect_env

case "${1:-}" in
    up)       shift; cmd_up "$@" ;;
    down)     shift; cmd_down "$@" ;;
    restart)  shift; cmd_restart "$@" ;;
    status)   cmd_status ;;
    logs)     shift; cmd_logs "$@" ;;
    build)    shift; cmd_build "$@" ;;
    migrate)  cmd_migrate ;;
    shell)    shift; cmd_shell "$@" ;;
    -h|--help|help|"")  usage ;;
    *)        err "Unknown command: $1"; echo ""; usage; exit 1 ;;
esac
