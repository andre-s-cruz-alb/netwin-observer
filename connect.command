#!/bin/sh
set -eu
socket_dir="/tmp/nwo-$(id -u)"
umask 077
if [ -L "$socket_dir" ]; then
  printf 'Diretório de socket inválido: %s\n' "$socket_dir" >&2
  exit 1
fi
mkdir -p "$socket_dir"
python3 -c 'import os,sys; p=sys.argv[1]; s=os.stat(p); assert s.st_uid == os.getuid(), "Diretório pertence a outro usuário"; os.chmod(p,0o700)' "$socket_dir"

# Carrega .env do mesmo diretório (apenas linhas KEY=VALUE com nomes válidos)
env_file="$(cd "$(dirname "$0")" && pwd)/.env"
if [ -f "$env_file" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in *[!A-Za-z0-9_]*|'') continue ;; esac
    export "$key=$val"
  done < "$env_file"
fi

case "${1:-backend}" in
  backend)    target=padmin@10.112.100.140; pswd_var=BACKEND_ENV_PSWD ;;
  frontend)   target=padmin@10.112.100.141; pswd_var=FRONTEND_ENV_PSWD ;;
  geoserver)  target=padmin@10.112.100.139; pswd_var=GEOSERVER_ENV_PSWD ;;
  database)   target=padmin@10.112.100.170; pswd_var=DATABASE_ENV_PSWD ;;
  docmanager) target=padmin@10.112.83.185;  pswd_var=DOCMANAGER_ENV_PSWD ;;
  *)          target="$1";                  pswd_var="" ;;
esac

# Resolve senha da variável de ambiente correspondente
password=""
if [ -n "$pswd_var" ]; then
  eval "password=\${${pswd_var}:-}"
fi

printf 'Conectando a %s (sessão master persistente)...\n' "$target"

if [ -n "$password" ] && command -v sshpass >/dev/null 2>&1; then
  exec sshpass -p "$password" ssh \
    -M -S "$socket_dir/%C" \
    -o ControlPersist=yes \
    -o ServerAliveInterval=30 \
    -o StrictHostKeyChecking=yes \
    -o BatchMode=no \
    "$target"
else
  if [ -n "$password" ]; then
    printf 'Aviso: sshpass não encontrado; a senha do .env não será usada automaticamente.\n' >&2
  fi
  exec ssh \
    -M -S "$socket_dir/%C" \
    -o ControlPersist=yes \
    -o ServerAliveInterval=30 \
    -o StrictHostKeyChecking=yes \
    "$target"
fi
