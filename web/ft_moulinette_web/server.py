"""Serveur HTTP local : fichiers statiques et API JSON des exécutions."""
import ipaddress
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from .jobs import JobManager, RunError

STATIC = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/static/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/static/style.css': ('style.css', 'text/css; charset=utf-8'),
}
SECURITY_HEADERS = {
    'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; base-uri 'none'; "
                               "form-action 'none'; frame-ancestors 'none'",
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Cache-Control': 'no-store',
}
MAX_BODY = 64 * 1024
REJECTED = object()  # read_json a déjà envoyé la réponse d'erreur
RUN_PATH = re.compile(r'^/api/runs/([0-9a-f]{12})$')


def is_loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host.strip('[]')).is_loopback
    except ValueError:
        return False


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, engine, allow_remote=False, progress=None):
        super().__init__(address, Handler)
        self.allow_remote = allow_remote
        self.manager = JobManager(engine, progress=progress)
        port = self.server_address[1]
        self.allowed_hosts = {f'{name}:{port}' for name in ('localhost', '127.0.0.1', '[::1]')}

    def server_close(self):
        self.manager.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'ft-moulinette-web'
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        if getattr(self.server, 'quiet', False):
            return
        super().log_message(format, *args)

    # --- réponses ---------------------------------------------------------
    def send(self, status, body=b'', content_type='application/json; charset=utf-8', headers=None):
        self.send_response(status)
        for name, value in {**SECURITY_HEADERS, **(headers or {})}.items():
            self.send_header(name, value)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_json(self, status, data):
        self.send(status, json.dumps(data, ensure_ascii=False).encode())

    def send_error_json(self, status, message):
        # Le corps éventuel n'a pas forcément été lu : ne pas réutiliser la connexion.
        self.close_connection = True
        self.send_json(status, dict(error=message))

    # --- garde-fous -------------------------------------------------------
    def trusted(self, mutating):
        """Bloque le DNS rebinding (Host) et les requêtes d'autres sites (Origin, Sec-Fetch-Site)."""
        host = self.headers.get('Host', '')
        if not self.server.allow_remote and host not in self.server.allowed_hosts:
            self.send_error_json(HTTPStatus.FORBIDDEN, 'En-tête Host non autorisé.')
            return False
        if mutating:
            origin = self.headers.get('Origin')
            site = self.headers.get('Sec-Fetch-Site')
            if (origin is not None and origin != f'http://{host}') or site not in (None, 'same-origin', 'none'):
                self.send_error_json(HTTPStatus.FORBIDDEN, 'Requête d’une autre origine refusée.')
                return False
        return True

    def read_json(self):
        if self.headers.get_content_type() != 'application/json':
            self.send_error_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, 'Corps JSON attendu.')
            return REJECTED
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self.send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, 'Corps de requête invalide ou trop grand.')
            return REJECTED
        try:
            return json.loads(self.rfile.read(length) or b'null')
        except ValueError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, 'JSON invalide.')
            return REJECTED

    # --- routes -----------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.trusted(False):
            return
        path = self.path.split('?', 1)[0]
        if path in STATIC:
            name, content_type = STATIC[path]
            body = resources.files(__package__).joinpath('static', name).read_bytes()
            return self.send(HTTPStatus.OK, body, content_type)
        if path == '/api/runs':
            return self.send_json(HTTPStatus.OK, dict(runs=self.server.manager.list()))
        match = RUN_PATH.match(path)
        if match:
            job = self.server.manager.get(match.group(1))
            if job is None:
                return self.send_error_json(HTTPStatus.NOT_FOUND, 'Exécution inconnue.')
            return self.send_json(HTTPStatus.OK, job)
        self.send_error_json(HTTPStatus.NOT_FOUND, 'Ressource introuvable.')

    def do_POST(self):
        if not self.trusted(True):
            return
        path = self.path.split('?', 1)[0]
        if path != '/api/runs':
            return self.send_error_json(HTTPStatus.NOT_FOUND, 'Ressource introuvable.')
        payload = self.read_json()
        if payload is REJECTED:
            return
        try:
            job = self.server.manager.submit(payload)
        except RunError as exc:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        self.send_json(HTTPStatus.ACCEPTED, job)

    def do_DELETE(self):
        if not self.trusted(True):
            return
        match = RUN_PATH.match(self.path.split('?', 1)[0])
        job = self.server.manager.cancel(match.group(1)) if match else None
        if job is None:
            return self.send_error_json(HTTPStatus.NOT_FOUND, 'Exécution inconnue.')
        self.send_json(HTTPStatus.OK, job)
