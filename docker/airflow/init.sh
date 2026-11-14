#!/usr/bin/env bash
set -euo pipefail

airflow db migrate

if ! airflow users list 2>/dev/null | grep -qw "${AIRFLOW_ADMIN_USER}"; then
  airflow users create \
    --username "${AIRFLOW_ADMIN_USER}" \
    --password "${AIRFLOW_ADMIN_PASSWORD}" \
    --firstname Admin --lastname Admin \
    --role Admin --email admin@example.com
fi

python /opt/airflow/render_connections.py /opt/airflow/connections /tmp/connections.json
airflow connections import /tmp/connections.json --overwrite
rm -f /tmp/connections.json
