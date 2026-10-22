"""Téléchargement poli d'un flux : User-Agent, en-têtes conditionnels, timeouts, backoff."""

import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

from gazette import __version__

USER_AGENT = f"LaGazetteBot/{__version__} (+https://github.com/ethannoe/Projet_la_gazette)"
TIMEOUT = (5, 20)  # connexion, lecture (secondes)
TENTATIVES = 3
ATTENTE = 2.0  # secondes avant le 1er nouvel essai, doublée à chaque fois
ATTENTE_MAX = 60.0
TRANSITOIRES = {429, 500, 502, 503, 504}


@dataclass
class Reponse:
    status: int
    content: bytes | None  # None sur un 304
    etag: str | None
    last_modified: str | None
    tentatives: int


class ErreurCollecte(Exception):
    def __init__(self, message: str, status: int | None, tentatives: int):
        super().__init__(message)
        self.status = status
        self.tentatives = tentatives


class ErreurTransitoire(ErreurCollecte):
    """503, timeout… : réessayée avec attente croissante, puis comptée comme un échec."""


class ErreurPermanente(ErreurCollecte):
    """404, 403… : inutile de réessayer tout de suite."""


def fetch_feed(
    url: str,
    etag: str | None = None,
    last_modified: str | None = None,
    *,
    tentatives: int = TENTATIVES,
    attente: float = ATTENTE,
    sleep: Callable[[float], None] = time.sleep,
) -> Reponse:
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    for essai in range(1, tentatives + 1):
        retry_after = None
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as exc:
            erreur = ErreurTransitoire(type(exc).__name__, None, essai)
        except requests.RequestException as exc:
            raise ErreurPermanente(type(exc).__name__, None, essai) from exc
        else:
            if r.status_code == 304:
                return Reponse(
                    304,
                    None,
                    r.headers.get("ETag", etag),
                    r.headers.get("Last-Modified", last_modified),
                    essai,
                )
            if r.status_code < 400:
                return Reponse(
                    r.status_code,
                    r.content,
                    r.headers.get("ETag"),
                    r.headers.get("Last-Modified"),
                    essai,
                )
            if r.status_code not in TRANSITOIRES:
                raise ErreurPermanente(f"HTTP {r.status_code}", r.status_code, essai)
            erreur = ErreurTransitoire(f"HTTP {r.status_code}", r.status_code, essai)
            retry_after = _retry_after(r)

        if essai < tentatives:
            sleep(min(retry_after or attente * 2 ** (essai - 1), ATTENTE_MAX))
    raise erreur


def _retry_after(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None
