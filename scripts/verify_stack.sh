#!/usr/bin/env bash
# Uso: scripts/verify_stack.sh dev|prod
set -uo pipefail

ENV_NAME="${1:?Uso: verify_stack.sh dev|prod}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}" || exit 1
ENV_FILE="env/.env.${ENV_NAME}"
[ -f "${ENV_FILE}" ] || { echo "FAIL: falta ${ENV_FILE}" >&2; exit 1; }
set -a
# shellcheck source=/dev/null
. "env/versions.env"
# shellcheck source=/dev/null
. "${ENV_FILE}"
set +a

compose() {
  docker compose --env-file env/versions.env --env-file "${ENV_FILE}" -p "sdg-${ENV_NAME}" "$@"
}
fail() { echo "FAIL: $*" >&2; exit 1; }

for svc in postgres silo airflow-apiserver airflow-scheduler airflow-dag-processor; do
  cid="$(compose ps -q "${svc}")"
  [ -n "${cid}" ] || fail "el servicio ${svc} no existe"
  st="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${cid}")"
  [ "${st}" = "healthy" ] || fail "el servicio ${svc} no está healthy (estado: ${st})"
done
echo "OK: servicios healthy"

curl -fsS -o /dev/null --max-time 10 "http://127.0.0.1:${PORT_AIRFLOW}/" \
  || fail "la UI de Airflow no responde en 127.0.0.1:${PORT_AIRFLOW}"
echo "OK: UI de Airflow"

for conn in silo_s3 warehouse_pg; do
  compose exec -T airflow-scheduler airflow connections get "${conn}" >/dev/null 2>&1 \
    || fail "la conexión ${conn} no existe en Airflow"
done
echo "OK: conexiones de Airflow"

compose run --rm -T mc-client stat local/data/demo/input/data2024.csv >/dev/null 2>&1 \
  || fail "no existe data/demo/input/data2024.csv en Silo"
echo "OK: bucket data con data2024.csv"

for db in "${AIRFLOW_DB_NAME}" "${WAREHOUSE_DB_NAME}"; do
  n="$(compose exec -T postgres psql -U "${POSTGRES_SUPERUSER}" -d postgres -Atc \
        "SELECT count(*) FROM pg_database WHERE datname='${db}'" 2>/dev/null)"
  [ "${n}" = "1" ] || fail "la base de datos ${db} no existe"
done
echo "OK: bases de datos"

echo "VERIFY OK"
