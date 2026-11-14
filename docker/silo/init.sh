#!/usr/bin/env bash
# Inicialización idempotente de Silo (servicio one-shot silo-init).
set -euo pipefail

mc alias set local "http://silo:9000" "${SILO_ROOT_USER}" "${SILO_ROOT_PASSWORD}"
mc mb --ignore-existing local/data

cat > /tmp/data-rw.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
     "Resource": ["arn:aws:s3:::data"]},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                                   "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
     "Resource": ["arn:aws:s3:::data/*"]}
  ]
}
JSON

mc admin policy rm local data-rw 2>/dev/null || true
mc admin policy create local data-rw /tmp/data-rw.json

if ! mc admin user info local "${SILO_APP_ACCESS_KEY}" >/dev/null 2>&1; then
  mc admin user add local "${SILO_APP_ACCESS_KEY}" "${SILO_APP_SECRET_KEY}"
fi
mc admin policy attach local data-rw --user "${SILO_APP_ACCESS_KEY}" || true

mc cp /seed/data2024.csv local/data/demo/input/data2024.csv
echo "silo-init OK"
