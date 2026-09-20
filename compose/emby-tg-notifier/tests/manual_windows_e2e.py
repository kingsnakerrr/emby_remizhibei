"""Run a real PotPlayer against a loopback-only fixture, never the user's Emby."""
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import wave

reports = []
mode = 'Resident' if '--resident' in sys.argv else 'Browser'
delivered = False
audio = io.BytesIO()
with wave.open(audio, 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(8000)
    wav.writeframes(bytes(8000 * 2 * 18))
audio = audio.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, data):
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        global delivered
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or '{}')
        if self.path == '/potplayer/poll':
            assert self.headers.get('Authorization') == 'Bearer '+'d'*43
            if reports and reports[-1]['event'] == 'stop':
                self.send_error(401)
            else:
                self.reply({'ticket':None if delivered else 't'*43})
                delivered=True
        elif self.path.startswith('/potplayer/claim/'):
            if mode == 'Resident':
                assert self.headers.get('Authorization') == 'Bearer '+'d'*43
            self.reply({'token':'s'*43, 'title':'HDZ-1234567890', 'resume':3, 'duration':18,
                        'url':f'http://127.0.0.1:{self.server.server_port}/test.wav'})
        elif self.path == '/potplayer/report' and self.headers.get('Authorization') == 'Bearer '+'s'*43:
            reports.append(body)
            self.reply({'ok':True})
        else:
            self.send_error(403)

    def do_HEAD(self):
        self.media(head=True)

    def do_GET(self):
        self.media()

    def media(self, head=False):
        if self.path != '/test.wav':
            self.send_error(404)
            return
        start, end = 0, len(audio)-1
        range_header = self.headers.get('Range')
        if range_header:
            parts = range_header.removeprefix('bytes=').split('-', 1)
            start = int(parts[0] or 0)
            end = min(end, int(parts[1]) if parts[1] else end)
        self.send_response(206 if range_header else 200)
        self.send_header('Content-Type', 'audio/wav')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end-start+1))
        if range_header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(audio)}')
        self.end_headers()
        if not head:
            self.wfile.write(audio[start:end+1])


with tempfile.TemporaryDirectory(prefix='jav-e2e-') as directory:
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        command = [os.environ['SystemRoot']+r'\System32\WindowsPowerShell\v1.0\powershell.exe',
                   '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(Path(__file__).with_name('windows_e2e.ps1')),
                   '-Origin', f'http://127.0.0.1:{server.server_port}', '-TestRoot', directory,
                   '-Mode',mode,
                   '-PlayerPath', r'C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe']
        result = subprocess.run(command, capture_output=True, timeout=60)
        print(result.stdout.decode(errors='replace')[-400:])
        print(result.stderr.decode(errors='replace')[-800:])
        assert result.returncode == 0, result.returncode
        assert len(reports) >= 2, reports
        assert reports[0]['position'] >= 3, reports
        assert reports[-1]['event'] == 'stop', reports
        assert reports[-1]['position'] >= 17, reports
        assert all(a['seq'] < b['seq'] for a,b in zip(reports,reports[1:])), reports
        print(mode, 'REAL PLAYER + HTTP CLAIM/PROGRESS/STOP:', reports)
    finally:
        server.shutdown()
        server.server_close()
