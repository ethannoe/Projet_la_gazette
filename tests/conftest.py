import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn():
    """Une connexion PostgreSQL isolée dans un schéma jetable."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL non défini : lancer les tests avec bin/test")
    import psycopg

    schema = f"test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"SET search_path TO {schema}")
        try:
            yield c
        finally:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


class FeedServer:
    """Un vrai serveur HTTP local qui joue le rôle d'un éditeur."""

    def __init__(self):
        self.routes: dict[str, dict] = {}
        self.requests: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, bytes]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append((self.path, dict(self.headers)))
                server.respond(self)

            def do_POST(self):  # le webhook d'alerte
                taille = int(self.headers.get("Content-Length", 0))
                server.posts.append((self.path, self.rfile.read(taille)))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}{path}"

    def route(self, path, *, body=b"", statuses=(200,), etag=None, headers=None):
        """`statuses` est joué dans l'ordre ; le dernier se répète."""
        self.routes[path] = {
            "body": body,
            "statuses": list(statuses),
            "etag": etag,
            "headers": headers or {},
        }

    def hits(self, path: str) -> int:
        return sum(1 for p, _ in self.requests if p == path)

    def respond(self, handler):
        route = self.routes.get(handler.path)
        if route is None:
            handler.send_response(404)
            handler.end_headers()
            return
        statuses = route["statuses"]
        status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
        if status != 200:
            handler.send_response(status)
            for name, value in route["headers"].items():
                handler.send_header(name, value)
            handler.end_headers()
            return
        if route["etag"] and handler.headers.get("If-None-Match") == route["etag"]:
            handler.send_response(304)
            handler.end_headers()
            return
        handler.send_response(200)
        handler.send_header("Content-Type", "application/xml")
        if route["etag"]:
            handler.send_header("ETag", route["etag"])
        handler.end_headers()
        handler.wfile.write(route["body"])


@pytest.fixture
def feed_server():
    server = FeedServer()
    yield server
    server.httpd.shutdown()
    server.httpd.server_close()
