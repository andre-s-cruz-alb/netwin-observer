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
case "${1:-backend}" in
  backend) target=padmin@10.112.100.140 ;;
  frontend) target=padmin@10.112.100.141 ;;
  geoserver) target=padmin@10.112.100.139 ;;
  database) target=padmin@10.112.100.170 ;;
  docmanager) target=padmin@10.112.83.185 ;;
  *) target="$1" ;;
esac
printf 'Conectando a %s: confirme a identidade do servidor. A senha será pedida pelo SSH.\n' "$target"
exec ssh -M -S "$socket_dir/%C" -o ControlPersist=no -o ServerAliveInterval=30 "$target"
