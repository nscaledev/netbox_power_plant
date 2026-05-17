#!/usr/bin/env bash
set -euo pipefail

DEVRUN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETBOX_RELEASE="${NETBOX_RELEASE:-4.2.3}"
NETBOX_SRC="${NETBOX_SRC:-$HOME/src/netbox-v${NETBOX_RELEASE}}"
NETBOX_PROJECT_DIR="${NETBOX_PROJECT_DIR:-$NETBOX_SRC/netbox}"
VENV_DIR="${VENV_DIR:-$HOME/.virtualenvs/netbox-${NETBOX_RELEASE}}"
STATE_DIR="${STATE_DIR:-$HOME/.config/netbox-power-plant-dev}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-$STATE_DIR/credentials.env}"
CONFIG_FILE="${CONFIG_FILE:-$NETBOX_PROJECT_DIR/netbox/configuration.py}"
ENV_FILE="${ENV_FILE:-$DEVRUN_DIR/.env}"
PLUGIN_NAME="netbox_power_plant"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-netbox_power_plant_devrun}"
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5434}"
REDIS_HOST_PORT="${REDIS_HOST_PORT:-6381}"

find_runserver_pids() {
    local pid
    local cwd

    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
        if [ "$cwd" = "$NETBOX_PROJECT_DIR" ]; then
            printf '%s\n' "$pid"
        fi
    done < <(pgrep -u "$USER" -f 'manage.py runserver' || true)
}

find_worker_pids() {
    local pid
    local cwd

    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
        if [ "$cwd" = "$NETBOX_PROJECT_DIR" ]; then
            printf '%s\n' "$pid"
        fi
    done < <(pgrep -u "$USER" -f 'manage.py rqworker default' || true)
}

runserver_is_running() {
    local pid
    while IFS= read -r pid; do
        if [ -n "$pid" ]; then
            return 0
        fi
    done < <(find_runserver_pids)
    return 1
}

worker_is_running() {
    local pid
    while IFS= read -r pid; do
        if [ -n "$pid" ]; then
            return 0
        fi
    done < <(find_worker_pids)
    return 1
}

stop_runserver() {
    local pid
    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        kill "$pid" >/dev/null 2>&1 || true
    done < <(find_runserver_pids)
}

stop_worker() {
    local pid
    while IFS= read -r pid; do
        [ -n "$pid" ] || continue
        kill "$pid" >/dev/null 2>&1 || true
    done < <(find_worker_pids)
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'Missing required command: %s\n' "$1" >&2
        exit 1
    }
}

ensure_state_dir() {
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
}

load_credentials() {
    if [ -f "$CREDENTIALS_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$CREDENTIALS_FILE"
        set +a
    fi
}

docker_compose() {
    (
        cd "$DEVRUN_DIR"
        docker compose -p "$COMPOSE_PROJECT_NAME" "$@"
    )
}

wait_for_postgres() {
    local attempt
    for attempt in $(seq 1 30); do
        if pg_isready -h 127.0.0.1 -p "$POSTGRES_HOST_PORT" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    printf 'PostgreSQL did not become ready in time.\n' >&2
    return 1
}

wait_for_redis() {
    local attempt
    for attempt in $(seq 1 30); do
        if redis-cli -h 127.0.0.1 -p "$REDIS_HOST_PORT" ping >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    printf 'Redis did not become ready in time.\n' >&2
    return 1
}
