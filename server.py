#!/usr/bin/env python3
"""NETWIN Observer: loopback-only, read-only SSH observability. Python 3.9+."""
import argparse
import concurrent.futures
import datetime
import http.server
import json
import os
from pathlib import Path
import secrets
import re
import shlex
import subprocess
import threading
import time
import urllib.parse

ROOT = Path(__file__).resolve().parent
HOSTS = json.loads((ROOT / 'hosts.json').read_text())
TOKEN = secrets.token_urlsafe(32)
PORT = 8765
LOCK = threading.BoundedSemaphore(8)
SSH_DIR = Path('/tmp') / f'nwo-{os.getuid()}'

def ssh_args(host):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1',
            '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=1',
            '-o', 'ControlMaster=no', '-o', f'ControlPath={SSH_DIR}/%C',
            f"{host['user']}@{host['address']}"]

def remote(host, command):
    with LOCK:
        try:
            r = subprocess.run(ssh_args(host) + [command], capture_output=True,
                               text=True, timeout=15)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Consulta SSH excedeu 15 segundos.')
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or 'Falha SSH')[-1800:])
        return r.stdout[:250000]

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def service_names(host):
    if not host.get('discoverServices'):
        return host['services']
    raw = remote(host, 'systemctl list-unit-files --type=service --no-pager --no-legend')
    names = []
    for line in raw.splitlines():
        parts = line.split()
        if parts and re.fullmatch(r'[A-Za-z0-9_.@:-]+\.service', parts[0]):
            name = parts[0]
            if re.search(r'netwin|jboss|wildfly|zookeeper|mongo|nginx|email|tomcat|stunnel|geoserver|docmanager', name, re.I):
                names.append(name)
    return sorted(set(names))

def snapshot(host):
    # All remote operations are fixed reads. No user-supplied shell commands.
    units = ' '.join(shlex.quote(s) for s in service_names(host))
    command = """export LC_ALL=C
printf '\\n@@IDENTITY\\n'; hostname; uptime
printf '\\n@@CPU\\n'; head -n 1 /proc/stat
printf '\\n@@MEMORY\\n'; cat /proc/meminfo
printf '\\n@@DISK\\n'; df -Pk /
printf '\\n@@SERVICES\\n'
""" + (f"systemctl show {units} --no-pager -p Id -p LoadState -p ActiveState -p SubState -p MainPID -p MemoryCurrent -p Result -p RemainAfterExit -p ControlGroup\n" if units else '') + "printf '\\n@@END\\n'"
    raw = remote(host, command)
    sections = {}
    for piece in raw.split('@@')[1:]:
        label, _, body = piece.partition('\n')
        sections[label] = body.strip()
    memory = {}
    for line in sections.get('MEMORY', '').splitlines():
        k, _, v = line.partition(':')
        if v.strip():
            memory[k] = int(v.split()[0]) * 1024
    total = memory.get('MemTotal', 0)
    available = memory.get('MemAvailable', memory.get('MemFree', 0))
    cpu = [int(x) for x in sections.get('CPU', '').split()[1:]]
    disk = sections.get('DISK', '').splitlines()
    disk_pct = int(disk[-1].split()[4].rstrip('%')) if len(disk) > 1 else None
    services = []
    for block in sections.get('SERVICES', '').split('\n\n'):
        fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        if fields.get('Id'):
            services.append(fields)
    return dict(at=now(), connected=True, identity=sections.get('IDENTITY', ''),
                memoryTotal=total, memoryUsed=total-available,
                memoryPercent=round(100*(total-available)/total, 1) if total else None,
                cpuTicks=cpu, diskPercent=disk_pct, services=services)

def metrics(host, name):
    port = host['metrics'][name]
    # Target URLs are determined by local configuration, never an API URL parameter.
    raw = remote(host, f'curl --fail --max-time 5 -sS http://127.0.0.1:{port}/metrics')
    samples = []
    for line in raw.splitlines():
        if not line or line.startswith('#'):
            continue
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            try:
                samples.append({'name': parts[0], 'value': float(parts[1])})
            except ValueError:
                pass
    # JSON excludes nonfinite Prometheus samples.
    import math
    return dict(at=now(), samples=[s for s in samples if math.isfinite(s['value'])], raw=raw)

def logs(host, unit):
    if unit not in service_names(host):
        raise ValueError('Serviço não permitido.')
    command = f'journalctl -u {shlex.quote(unit)} -n 150 --since "30 minutes ago" --no-pager -o short-iso 2>&1'
    return dict(at=now(), text=remote(host, command))

# Forwarding is owned by this app and attached to an existing authenticated SSH master.
TUNNELS = {}
TUNNEL_LOCK = threading.Lock()

def forward_command(host, operation, spec=None):
    args = ssh_args(host)[:-1] + ['-O', operation]
    if spec:
        args += ['-o', 'ExitOnForwardFailure=yes', '-L', spec]
    args += [f"{host['user']}@{host['address']}"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
    except subprocess.TimeoutExpired:
        raise RuntimeError('O controle do túnel SSH excedeu o tempo limite.')
    if result.returncode:
        raise RuntimeError((result.stderr or 'Abra connect.command para este host antes de criar o túnel.')[-1800:])
    return result

def tunnel_list(host_id):
    host = HOSTS[host_id]
    with TUNNEL_LOCK:
        active = [key for key in TUNNELS if key[0] == host_id]
        if active:
            try:
                forward_command(host, 'check')
            except RuntimeError:
                for key in active:
                    TUNNELS.pop(key, None)
        return [dict(id=name, **cfg, active=(host_id, name) in TUNNELS)
                for name, cfg in host.get('forwards', {}).items()]

def tunnel_action(host_id, name, action):
    host = HOSTS[host_id]
    cfg = host.get('forwards', {}).get(name)
    if cfg is None or action not in ('start', 'stop'):
        raise ValueError('Encaminhamento ou ação não permitido.')
    key = (host_id, name)
    spec = f"127.0.0.1:{cfg['localPort']}:127.0.0.1:{cfg['remotePort']}"
    with TUNNEL_LOCK:
        if action == 'start':
            forward_command(host, 'check')
            if key not in TUNNELS:
                forward_command(host, 'forward', spec)
                TUNNELS[key] = spec
        elif key in TUNNELS:
            try:
                forward_command(host, 'cancel', TUNNELS[key])
            except RuntimeError as error:
                try:
                    forward_command(host, 'check')
                except RuntimeError:
                    TUNNELS.pop(key, None)
                raise error
            TUNNELS.pop(key, None)
    return dict(ok=True)

def close_tunnels():
    with TUNNEL_LOCK:
        for (host_id, name), spec in list(TUNNELS.items()):
            try:
                forward_command(HOSTS[host_id], 'cancel', spec)
            except RuntimeError:
                pass
        TUNNELS.clear()

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Do not write session tokens or log contents to server access logs.

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{PORT}', f'localhost:{PORT}'):
            return self.reply(403, {'error': 'Host não permitido.'})
        if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self.reply(403, {'error': 'Origem não permitida.'})
        if not secrets.compare_digest(self.headers.get('X-Observer-Token', ''), TOKEN):
            return self.reply(401, {'error': 'Sessão não autenticada.'})
        parts = urllib.parse.urlsplit(self.path).path.strip('/').split('/')
        if len(parts) != 3 or parts[0] != 'api' or parts[1] not in HOSTS or parts[2] != 'tunnels':
            return self.reply(404, {'error': 'Recurso não encontrado.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                raise ValueError('Requisição inválida.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Requisição inválida.')
            return self.reply(200, tunnel_action(parts[1], body.get('id', ''), body.get('action', '')))
        except (ValueError, TypeError) as e:
            return self.reply(400, {'error': str(e)})
        except Exception as e:
            return self.reply(502, {'error': str(e)})

    def do_GET(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{PORT}', f'localhost:{PORT}'):
            return self.reply(403, {'error': 'Host não permitido.'})
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self.reply(403, {'error': 'Origem não permitida.'})
        url = urllib.parse.urlsplit(self.path)
        if url.path.startswith('/api/'):
            if not secrets.compare_digest(self.headers.get('X-Observer-Token', ''), TOKEN):
                return self.reply(401, {'error': 'Abra a URL completa exibida no Terminal para autenticar esta sessão.'})
            try:
                if url.path == '/api/hosts':
                    return self.reply(200, HOSTS)
                parts = url.path.strip('/').split('/')
                if len(parts) != 3 or parts[1] not in HOSTS:
                    return self.reply(404, {'error': 'Recurso não encontrado.'})
                host, action = HOSTS[parts[1]], parts[2]
                query = urllib.parse.parse_qs(url.query)
                if action == 'snapshot':
                    result = snapshot(host)
                elif action == 'metrics':
                    name = query.get('name', [''])[0]
                    if name not in host['metrics']:
                        raise ValueError('Métrica não permitida.')
                    result = metrics(host, name)
                elif action == 'tunnels':
                    result = tunnel_list(parts[1])
                elif action == 'logs':
                    result = logs(host, query.get('unit', [''])[0])
                else:
                    return self.reply(404, {'error': 'Recurso não encontrado.'})
                return self.reply(200, result)
            except ValueError as e:
                return self.reply(400, {'error': str(e)})
            except Exception as e:
                return self.reply(502, {'error': str(e), 'at': now()})
        static = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if url.path not in static:
            return self.reply(404, {'error': 'Não encontrado.'})
        file, kind = static[url.path]
        return self.reply(200, (ROOT/'web'/file).read_bytes(), kind)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    PORT = args.port
    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'NETWIN Observer — somente consulta\nAbra: http://127.0.0.1:{PORT}/#token={TOKEN}', flush=True)
    print('Ctrl+C para encerrar. Autenticação SSH via chave/agent ou sessão compartilhada.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        close_tunnels()
        server.server_close()
