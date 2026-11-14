#!/usr/bin/env bash
# Uso: tests/e2e/run_e2e.sh dev|prod
# Respeta AIRFLOW_IMAGE exportada en el shell (tiene prioridad sobre el .env).
set -euo pipefail

ENV_NAME="${1:?Uso: run_e2e.sh dev|prod}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

MAKE=(make "ENV=${ENV_NAME}")
compose() {
  docker compose --env-file env/versions.env --env-file "env/.env.${ENV_NAME}" \
    -p "sdg-${ENV_NAME}" "$@"
}
WORK="$(mktemp -d)"

cleanup() {
  rc=$?
  if [ "${rc}" -ne 0 ]; then
    echo "E2E FALLÓ (código ${rc}); guardando logs en e2e-logs/" >&2
    mkdir -p e2e-logs
    for svc in $(compose ps -a --services 2>/dev/null); do
      compose logs --no-color "${svc}" >"e2e-logs/${svc}.log" 2>&1 || true
    done
    compose exec -T airflow-scheduler bash -c 'cat /opt/airflow/logs/dag_id=mdf_run/*/*/*.log 2>/dev/null' \
      >e2e-logs/dag-tasks.log 2>&1 || true
  fi
  "${MAKE[@]}" destroy FORCE=1 >/dev/null 2>&1 || true
  rm -rf "${WORK}"
  exit "${rc}"
}
trap cleanup EXIT

fail() { echo "ASSERT FAIL: $*" >&2; exit 1; }

WAREHOUSE_DB_NAME="$(grep -E '^WAREHOUSE_DB_NAME=' "env/.env.${ENV_NAME}.example" | cut -d= -f2)"

sql_count() {  # tabla -> filas
  compose exec -T postgres sh -c \
    "psql -U \"\$POSTGRES_USER\" -d ${WAREHOUSE_DB_NAME} -Atc 'SELECT count(*) FROM $1'" | tr -d '[:space:]'
}

parquet_count() {  # last|historic -> filas
  compose exec -T airflow-scheduler python - "$1" <<'PY'
import os, sys
import pandas as pd
import s3fs
fs = s3fs.S3FileSystem(
    key=os.environ["S3_ACCESS_KEY"], secret=os.environ["S3_SECRET_KEY"],
    client_kwargs={"endpoint_url": os.environ["S3_ENDPOINT_URL"]},
    config_kwargs={"s3": {"addressing_style": "path"}},
)
print(len(pd.read_parquet("data/demo/output/" + sys.argv[1], filesystem=fs)))
PY
}

assert_eq() {  # nombre esperado obtenido
  [ "$2" = "$3" ] || fail "$1: esperado $2, obtenido $3"
  echo "  ok: $1 = $3"
}

assert_2024() {
  assert_eq "demo" 15410 "$(sql_count demo)"
  assert_eq "raw_demo" 15410 "$(sql_count raw_demo)"
  assert_eq "last" 15410 "$(parquet_count last)"
  assert_eq "historic" 15410 "$(parquet_count historic)"
}

assert_2025() {
  assert_eq "demo" 15410 "$(sql_count demo)"
  assert_eq "raw_demo" 30820 "$(sql_count raw_demo)"
  assert_eq "historic" 30820 "$(parquet_count historic)"
  assert_eq "last" 15410 "$(parquet_count last)"
}

trigger_dag() {  # year
  local year="$1" run_id state
  run_id="e2e_$(date +%s)_${year}"
  compose exec -T airflow-scheduler airflow dags trigger mdf_run \
    --run-id "${run_id}" --conf "{\"year\": ${year}}" >/dev/null 2>&1
  local deadline=$((SECONDS + 300))
  while [ "${SECONDS}" -lt "${deadline}" ]; do
    state="$(compose exec -T airflow-scheduler airflow dags list-runs mdf_run -o json 2>/dev/null \
      | python3 -c "import sys,json; r=[x for x in json.load(sys.stdin) if x.get('run_id', x.get('dag_run_id'))=='${run_id}']; print(r[0]['state'] if r else 'none')")"
    case "${state}" in
      success) echo "  ok: DAG ${year} success"; return 0 ;;
      failed) fail "el DAG con year=${year} terminó en failed" ;;
    esac
    sleep 5
  done
  fail "timeout (300 s) esperando el DAG con year=${year}"
}

wait_dag_parsed() {
  for _ in $(seq 1 60); do
    if compose exec -T airflow-scheduler airflow dags list 2>/dev/null | grep -q mdf_run; then
      compose exec -T airflow-scheduler airflow dags unpause mdf_run >/dev/null 2>&1
      return 0
    fi
    sleep 3
  done
  fail "el DAG mdf_run no aparece"
}

assert_merge_log_dag() {
  compose exec -T airflow-scheduler bash -c 'cat /opt/airflow/logs/dag_id=mdf_run/*/task_id=run_dataflow/*.log' \
    | grep -Eq 'rows_updated\W+5\W' || fail "el log de la tarea no contiene rows_updated 5"
  echo "  ok: log de tarea con rows_updated 5"
}

if [ -z "${AIRFLOW_IMAGE:-}" ]; then
  "${MAKE[@]}" build >/dev/null
fi
"${MAKE[@]}" destroy FORCE=1 >/dev/null 2>&1 || true

echo "== Ruta A (CLI) =="
"${MAKE[@]}" env up verify
"${MAKE[@]}" run YEAR=2024
assert_2024
"${MAKE[@]}" load-2025
"${MAKE[@]}" run YEAR=2025 | tee "${WORK}/run2025.log"
grep -Eq '"rows_updated": 5[,}]' "${WORK}/run2025.log" || fail "el log del merge no contiene rows_updated: 5"
echo "  ok: log del merge con rows_updated 5"
assert_2025
"${MAKE[@]}" destroy FORCE=1

echo "== Ruta B (DAG) =="
"${MAKE[@]}" up verify
wait_dag_parsed
trigger_dag 2024
assert_2024
"${MAKE[@]}" load-2025
trigger_dag 2025
assert_merge_log_dag
assert_2025

echo "== Checks =="
PY="${PYTHON:-python3}"
out="$("${PY}" checks/diff_rows.py --old data/data2024.csv --new data/data2025.csv --out "${WORK}/chk")"
echo "${out}" | grep -q "cambiadas=8" || fail "diff_rows: se esperaban 8 cambiadas"
echo "  ok: diff_rows 8 cambiadas"
"${PY}" checks/dq_both_sexes.py --file data/data2024.csv --out "${WORK}/chk" | tail -1 | grep -q "STATUS: OK" \
  || fail "dq 2024 debía ser OK"
set +e
"${PY}" checks/dq_both_sexes.py --file data/data2025.csv --out "${WORK}/chk" >"${WORK}/dq2025.txt"
rc=$?
set -e
[ "${rc}" -eq 1 ] || fail "dq 2025 debía salir con código 1 (obtenido ${rc})"
tail -1 "${WORK}/dq2025.txt" | grep -q "STATUS: PENDING_REVIEW" || fail "dq 2025 sin PENDING_REVIEW"
[ "$(grep -c RULE_VIOLATION "${WORK}/chk/dq_violations.csv")" = 2 ] || fail "dq 2025: se esperaban 2 RULE_VIOLATION"
echo "  ok: checks A y B"

echo "E2E OK"
