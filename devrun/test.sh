#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/common.sh"

FAST_TEST_LABELS=(
    netbox_power_plant.tests.test_plugin_config.PluginConfigTestCase
    netbox_power_plant.tests.test_phase_1a_models.Phase1AModelTestCase
    netbox_power_plant.tests.test_phase_1b_models.Phase1BModelTestCase
    netbox_power_plant.tests.test_phase_1b_graph.Phase1BGraphTestCase
    netbox_power_plant.tests.test_phase_1b_validation.Phase1BValidationTestCase
    netbox_power_plant.tests.test_phase_1a_views.Phase1AViewTestCase
    netbox_power_plant.tests.test_phase_1b_views.Phase1BViewTestCase
    netbox_power_plant.tests.test_phase_1a_api.Phase1AAPITestCase
    netbox_power_plant.tests.test_phase_1b_api.Phase1BAPITestCase
)

CONTRACT_TEST_LABELS=(
    netbox_power_plant.tests
)

load_compose_env() {
    if [ -f "$ENV_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$ENV_FILE"
        set +a
    fi
}

prepare_test_environment() {
    load_credentials
    load_compose_env

    export POSTGRES_DB="${POSTGRES_DB:-netbox}"
    export POSTGRES_USER="${POSTGRES_USER:-netbox}"
    export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${NETBOX_DATABASE_PASSWORD:-netbox}}"
    export NETBOX_CONFIGURATION="${NETBOX_CONFIGURATION:-netbox_power_plant.tests.netbox_configuration}"
    export NETBOX_POWER_PLANT_ENABLE=1
    export NETBOX_TEST_DB_NAME="${NETBOX_TEST_DB_NAME:-$POSTGRES_DB}"
    export NETBOX_TEST_DB_USER="${NETBOX_TEST_DB_USER:-$POSTGRES_USER}"
    export NETBOX_TEST_DB_PASSWORD="${NETBOX_TEST_DB_PASSWORD:-$POSTGRES_PASSWORD}"
    export NETBOX_TEST_DB_HOST="${NETBOX_TEST_DB_HOST:-127.0.0.1}"
    export NETBOX_TEST_DB_PORT="${NETBOX_TEST_DB_PORT:-$POSTGRES_HOST_PORT}"
    export NETBOX_TEST_DB_TEST_NAME="${NETBOX_TEST_DB_TEST_NAME:-test_${NETBOX_TEST_DB_NAME}_power_plant}"
    export NETBOX_TEST_REDIS_HOST="${NETBOX_TEST_REDIS_HOST:-127.0.0.1}"
    export NETBOX_TEST_REDIS_PORT="${NETBOX_TEST_REDIS_PORT:-$REDIS_HOST_PORT}"
    export NETBOX_TEST_REDIS_PASSWORD="${NETBOX_TEST_REDIS_PASSWORD:-}"
}

run_django_tests() {
    local -a labels=("$@")

    (
        cd "$NETBOX_PROJECT_DIR"
        exec "$VENV_DIR/bin/python" manage.py test --keepdb --noinput "${labels[@]}"
    )
}

main() {
    require_command docker
    require_command pg_isready
    require_command redis-cli

    prepare_test_environment
    docker_compose up -d postgres redis >/dev/null
    wait_for_postgres
    wait_for_redis

    case "${1:-contract}" in
        fast)
            shift || true
            run_django_tests "${FAST_TEST_LABELS[@]}" "$@"
            ;;
        contract)
            shift || true
            run_django_tests "${CONTRACT_TEST_LABELS[@]}" "$@"
            ;;
        full)
            shift || true
            run_django_tests netbox_power_plant.tests "$@"
            ;;
        *)
            run_django_tests "$@"
            ;;
    esac
}

main "$@"
