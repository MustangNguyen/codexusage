#!/usr/bin/env python3
"""Read-only Codex usage dashboard; serves only aggregate usage on loopback."""
from contextlib import closing
import argparse
import multiprocessing
import os
import json
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path.home() / '.codex'
HERE = Path(__file__).resolve().parent
ZONE = ZoneInfo('Asia/Bangkok')
KEYS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens')

class UsageIndex:
    def __init__(self, root=ROOT):
        self.root = root
        self.files = {}
        self.records = {}
        self.titles = {}
        self.lock = threading.Lock()
        self.error = None
        self.updated = None
        self.ready = False

    def scan(self):
        for folder in ('sessions', 'archived_sessions'):
            for path in (self.root / folder).rglob('*.jsonl'):
                try:
                    stat = path.stat()
                    state = self.files.get(str(path))
                    if state is None or stat.st_size < state['offset'] or state['inode'] != stat.st_ino:
                        state = {'offset': 0, 'model': 'unknown', 'thread': path.stem, 'inode': stat.st_ino}
                    if state.get('size') == stat.st_size and state.get('mtime') == stat.st_mtime_ns:
                        continue
                    state.update(size=stat.st_size, mtime=stat.st_mtime_ns)
                    with path.open('rb') as stream:
                        stream.seek(state['offset'])
                        while True:
                            line = stream.readline(1024 * 1024)
                            if line and not line.endswith(b'\n') and len(line) == 1024 * 1024:
                                while line and not line.endswith(b'\n'):
                                    line = stream.readline(1024 * 1024)
                                if line.endswith(b'\n'):
                                    state['offset'] = stream.tell()
                                    continue
                                break
                            if not line or not line.endswith(b'\n'):
                                break  # Retry incomplete lines on the next scan.
                            state['offset'] = stream.tell()
                            if not any(tag in line[:250] for tag in (b'turn_context', b'session_meta', b'token_usage_record')):
                                continue
                            try:
                                item = json.loads(line)
                            except (ValueError, UnicodeDecodeError):
                                continue
                            p = item.get('payload', {})
                            kind = item.get('type')
                            if kind == 'session_meta':
                                state['thread'] = p.get('id', state['thread'])
                            elif kind == 'turn_context':
                                state['model'] = p.get('model') or 'unknown'
                            elif kind == 'token_usage_record':
                                thread = p.get('thread_id') or state['thread']
                                rid = p.get('response_id') or f"{thread}:{p.get('turn_id')}:{item.get('ordinal', state['offset'])}"
                                with self.lock:
                                    self.records[rid] = {'id': rid, 'thread': thread, 'model': p.get('model') or state['model'], 'timestamp': item['timestamp'], **{k: int(p.get('usage', {}).get(k, 0) or 0) for k in KEYS}}
                    self.files[str(path)] = state
                except FileNotFoundError:
                    continue
        db = self.root / 'state_5.sqlite'
        if db.exists():
            try:
                with closing(sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=1)) as conn:
                    self.titles = {tid: (title[:140] + '…' if len(title) > 140 else title) for tid, title in conn.execute('select id,substr(title,1,141) from threads') if title}
            except sqlite3.Error:
                pass
        self.updated = datetime.now(ZONE).isoformat()
        self.ready = True

    def snapshot(self, day):
        with self.lock:
            rows = []
            for row in self.records.values():
                try:
                    if datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')).astimezone(ZONE).date().isoformat() == day:
                        rows.append(row)
                except ValueError:
                    continue
            rows.sort(key=lambda r: r['timestamp'])
            return {'date': day, 'timezone': str(ZONE), 'ready': self.ready, 'updated': self.updated, 'error': self.error, 'files': len(self.files), 'titles': {r['thread']: self.titles.get(r['thread'], r['thread']) for r in rows}, 'rows': rows}

    def watch(self):
        while True:
            try:
                self.scan()
                self.error = None
            except Exception as exc:
                self.error = str(exc)
            time.sleep(3)

CACHE = HERE / 'cache'

def collect_usage():
    os.nice(10)
    index = UsageIndex()
    CACHE.mkdir(exist_ok=True)
    while True:
        started = time.monotonic()
        try:
            index.scan()
            grouped = {datetime.now(ZONE).date().isoformat(): []}
            for row in index.records.values():
                day = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')).astimezone(ZONE).date().isoformat()
                grouped.setdefault(day, []).append(row)
            for day, rows in grouped.items():
                rows.sort(key=lambda r: r['timestamp'])
                result = {'date': day, 'timezone': str(ZONE), 'ready': True, 'updated': index.updated, 'error': None, 'files': len(index.files), 'titles': {r['thread']: index.titles.get(r['thread'], r['thread']) for r in rows}, 'rows': rows}
                temp = CACHE / (day + '.tmp')
                temp.write_text(json.dumps(result, ensure_ascii=False))
                temp.replace(CACHE / (day + '.json'))
            health = CACHE / 'health.tmp'
            health.write_text(json.dumps({'ready': True, 'updated': index.updated, 'files': len(index.files)}))
            health.replace(CACHE / 'health.json')
            print(f'Usage scan: {len(index.records)} records, {time.monotonic()-started:.2f}s', flush=True)
        except Exception as exc:
            print(f'Usage scan error: {exc}', flush=True)
        time.sleep(3)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/api/usage':
            day = parse_qs(url.query).get('date', [datetime.now(ZONE).date().isoformat()])[0]
            try:
                datetime.strptime(day, '%Y-%m-%d')
            except ValueError:
                self.send_error(400, 'Invalid date')
                return
            path = CACHE / (day + '.json')
            result = json.loads(path.read_bytes()) if path.exists() else {'date': day, 'ready': False, 'updated': None, 'error': None, 'files': 0, 'titles': {}, 'rows': []}
            health_path = CACHE / 'health.json'
            health = json.loads(health_path.read_bytes()) if health_path.exists() else {}
            if health.get('ready') and not result['ready']:
                result.update(ready=True, updated=health['updated'], files=health['files'])
            if health.get('updated') or result.get('updated'):
                age = (datetime.now(ZONE) - datetime.fromisoformat(health.get('updated') or result['updated'])).total_seconds()
                if age > 30:
                    result['error'] = f'Dữ liệu đã dừng cập nhật {int(age)} giây. Chạy codexusage để phục hồi.'
            body = json.dumps(result, ensure_ascii=False).encode()
            content_type = 'application/json; charset=utf-8'
        elif url.path in ('/', '/index.html'):
            body = (HERE / 'index.html').read_bytes()
            content_type = 'text/html; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    collector = multiprocessing.Process(target=collect_usage, daemon=True)
    collector.start()
    ThreadingHTTPServer.request_queue_size = 64
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
