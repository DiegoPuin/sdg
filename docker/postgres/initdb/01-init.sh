#!/usr/bin/env bash
# Se ejecuta solo con el volumen vacío. Idempotente.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v adb="$AIRFLOW_DB_NAME" -v au="$AIRFLOW_DB_USER" -v ap="$AIRFLOW_DB_PASS" \
  -v wdb="$WAREHOUSE_DB_NAME" -v wu="$WAREHOUSE_DB_USER" -v wp="$WAREHOUSE_DB_PASS" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'au', :'ap')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'au')
\gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'wu', :'wp')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'wu')
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'adb', :'au')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'adb')
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'wdb', :'wu')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'wdb')
\gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'adb') \gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'wdb') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'adb', :'au') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'wdb', :'wu') \gexec
SQL
