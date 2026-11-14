#!/usr/bin/env bash
# Uso: scripts/gen_env.sh dev|prod — genera env/.env.<ENV> desde el .example. No sobrescribe.
set -euo pipefail

ENV_NAME="${1:?Uso: gen_env.sh dev|prod}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/env/.env.${ENV_NAME}.example"
DST="${ROOT}/env/.env.${ENV_NAME}"

[ -f "${SRC}" ] || { echo "No existe ${SRC}" >&2; exit 1; }
if [ -f "${DST}" ]; then
  echo "${DST} ya existe; no se sobrescribe."
  exit 0
fi

rand() { python3 -c 'import secrets,string,sys;a=string.ascii_letters+string.digits;print("".join(secrets.choice(a) for _ in range(int(sys.argv[1]))))' "${1:-24}"; }
fernet() { python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())'; }

umask 077
: > "${DST}"
while IFS= read -r line || [ -n "${line}" ]; do
  case "${line}" in
    *"<random>"*) line="${line/<random>/$(rand 24)}" ;;
    *"<generated>"*) line="${line/<generated>/$(fernet)}" ;;
  esac
  printf '%s\n' "${line}" >> "${DST}"
done < "${SRC}"
echo "Generado ${DST}"
