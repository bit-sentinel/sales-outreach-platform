#!/usr/bin/env bash
# ==============================================================================
# OutreachAI – Production Deployment Script
# Run on a fresh Hetzner CX32 (Ubuntu 24.04 LTS)
#
# First-time setup:  bash deploy.sh setup
# Deploy / redeploy: bash deploy.sh deploy
# View logs:         bash deploy.sh logs
# Run DB migrations: bash deploy.sh migrate
# ==============================================================================

set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"
APP_DIR="/opt/outreachai"

# ── Colours ───────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Helpers ───────────────────────────────────────────────
require_env() {
  [[ -f .env.prod ]] || error ".env.prod not found. Copy .env.prod.example and fill in values."
  source .env.prod
  if [[ -z "${SECRET_KEY:-}"        ]]; then error "SECRET_KEY is not set in .env.prod"; fi
  if [[ -z "${JWT_SECRET_KEY:-}"    ]]; then error "JWT_SECRET_KEY is not set in .env.prod"; fi
  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then error "POSTGRES_PASSWORD is not set in .env.prod"; fi
  if [[ -z "${DOMAIN:-}"            ]]; then error "DOMAIN is not set in .env.prod"; fi
  if [[ "${SECRET_KEY}" == *"change-me"* ]]; then error "SECRET_KEY still has placeholder value — generate a real one"; fi
}

# ──────────────────────────────────────────────────────────
# COMMAND: setup
# Installs Docker on a fresh Ubuntu server
# ──────────────────────────────────────────────────────────
cmd_setup() {
  info "Setting up server..."

  # Docker
  if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    info "Docker installed."
  else
    info "Docker already installed: $(docker --version)"
  fi

  # Firewall (UFW)
  if command -v ufw &>/dev/null; then
    info "Configuring firewall..."
    ufw allow OpenSSH
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 443/udp   # HTTP/3
    ufw --force enable
    info "Firewall configured."
  fi

  # Swap (recommended for 8GB server running 6 containers)
  if [[ ! -f /swapfile ]]; then
    info "Creating 2GB swapfile..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    info "Swapfile created."
  fi

  info "Server setup complete."
  echo ""
  warn "Next steps:"
  echo "  1. Upload your project files to this server (scp, rsync, or git clone)"
  echo "  2. Copy .env.prod.example to .env.prod and fill in all values"
  echo "  3. Edit Caddyfile — replace YOUR_DOMAIN with your actual domain"
  echo "  4. Point your domain's DNS A record to this server's IP"
  echo "  5. Run: bash deploy.sh deploy"
}

# ──────────────────────────────────────────────────────────
# COMMAND: deploy
# Builds images, runs migrations, starts all services
# ──────────────────────────────────────────────────────────
cmd_deploy() {
  require_env

  # Swap YOUR_DOMAIN placeholder in Caddyfile if not already done
  if grep -q "YOUR_DOMAIN" Caddyfile; then
    info "Patching Caddyfile with domain: ${DOMAIN}"
    sed -i "s/YOUR_DOMAIN/${DOMAIN}/g" Caddyfile
  fi

  info "Pulling base images..."
  $COMPOSE pull postgres redis caddy

  info "Building application images..."
  $COMPOSE build --no-cache api celery-worker celery-beat frontend

  info "Starting infrastructure (postgres + redis)..."
  $COMPOSE up -d postgres redis

  info "Waiting for postgres to be healthy..."
  until $COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" &>/dev/null; do
    echo -n "."
    sleep 2
  done
  echo ""

  info "Running database migrations..."
  $COMPOSE run --rm api alembic upgrade head

  info "Starting all services..."
  $COMPOSE up -d

  info "Deployment complete!"
  echo ""
  echo "  Frontend: https://${DOMAIN}"
  echo ""
  echo "  Useful commands:"
  echo "    bash deploy.sh logs       — tail all logs"
  echo "    bash deploy.sh status     — container health"
  echo "    bash deploy.sh migrate    — run DB migrations only"
}

# ──────────────────────────────────────────────────────────
# COMMAND: migrate
# Run Alembic migrations against the running DB
# ──────────────────────────────────────────────────────────
cmd_migrate() {
  require_env
  info "Running database migrations..."
  $COMPOSE run --rm api alembic upgrade head
  info "Migrations complete."
}

# ──────────────────────────────────────────────────────────
# COMMAND: logs
# Tail logs for all (or a specific) service
# ──────────────────────────────────────────────────────────
cmd_logs() {
  require_env
  local service="${1:-}"
  if [[ -n "$service" ]]; then
    $COMPOSE logs -f "$service"
  else
    $COMPOSE logs -f
  fi
}

# ──────────────────────────────────────────────────────────
# COMMAND: status
# Show running containers and health
# ──────────────────────────────────────────────────────────
cmd_status() {
  require_env
  $COMPOSE ps
}

# ──────────────────────────────────────────────────────────
# COMMAND: restart
# Restart one or all services without rebuilding
# ──────────────────────────────────────────────────────────
cmd_restart() {
  require_env
  local service="${1:-}"
  if [[ -n "$service" ]]; then
    info "Restarting ${service}..."
    $COMPOSE restart "$service"
  else
    info "Restarting all services..."
    $COMPOSE restart
  fi
  info "Done."
}

# ──────────────────────────────────────────────────────────
# COMMAND: update
# Pull latest code and redeploy with zero-downtime restart
# ──────────────────────────────────────────────────────────
cmd_update() {
  require_env
  info "Rebuilding and restarting services..."
  $COMPOSE build --no-cache api celery-worker celery-beat frontend
  $COMPOSE run --rm api alembic upgrade head
  $COMPOSE up -d --no-deps api celery-worker celery-beat frontend
  info "Update complete."
}

# ──────────────────────────────────────────────────────────
# COMMAND: backup
# Dump postgres to a timestamped .sql.gz file
# ──────────────────────────────────────────────────────────
cmd_backup() {
  require_env
  local filename="backup_$(date +%Y%m%d_%H%M%S).sql.gz"
  info "Backing up database to ${filename}..."
  $COMPOSE exec -T postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${filename}"
  info "Backup saved: ${filename}"
}

# ──────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────
case "${1:-help}" in
  setup)   cmd_setup   ;;
  deploy)  cmd_deploy  ;;
  migrate) cmd_migrate ;;
  logs)    cmd_logs "${2:-}" ;;
  status)  cmd_status  ;;
  update)  cmd_update  ;;
  backup)  cmd_backup  ;;
  restart) cmd_restart "${2:-}" ;;
  *)
    echo "Usage: bash deploy.sh <command>"
    echo ""
    echo "Commands:"
    echo "  setup    — Install Docker + configure firewall on fresh Ubuntu server"
    echo "  deploy   — Build images, run migrations, start all services"
    echo "  update   — Rebuild and restart app containers (after code changes)"
    echo "  migrate  — Run Alembic DB migrations only"
    echo "  logs     — Tail logs (optionally pass service name: logs api)"
    echo "  status   — Show container health"
    echo "  restart  — Restart all or one service without rebuilding (restart api)"
    echo "  backup   — Dump PostgreSQL to a .sql.gz file"
    ;;
esac
