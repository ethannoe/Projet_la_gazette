"""Transforme un flux RSS 2.0 ou Atom en items bruts.

feedparser unifie les deux formats : `pubDate` / `updated` → published / updated,
`description` / `summary` → summary, `guid` / `id` → id ; il gère aussi les
encodages et la plupart des formats de date. On ne garde que titre, extrait,
lien, date et rubrique (cf. docs/donnees.md) : ni texte intégral
(`content:encoded`), ni image, ni auteur.
"""

import html
import re
from calendar import timegm
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

MAX_RESUME = 500  # au-delà, ce n'est plus un extrait
MAX_BRUT = 1000  # extrait brut gardé dans le payload
PARAMS_DE_SUIVI = ("utm_", "xtor")  # ajoutés par les éditeurs, changent d'un passage à l'autre

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


class FeedError(ValueError):
    """Le contenu reçu n'est pas un flux lisible."""


def clean_text(value: str | None) -> str:
    """Retire les balises HTML, décode les entités et normalise les espaces."""
    text = html.unescape(_TAG.sub(" ", value or ""))
    return _SPACES.sub(" ", text).strip()


def truncate(text: str, limit: int = MAX_RESUME) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def normalize_link(link: str | None) -> str:
    """Le lien sert de clé : on retire le fragment et les paramètres de suivi."""
    parts = urlsplit((link or "").strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(PARAMS_DE_SUIVI)
    ]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urlencode(query), ""))


def parse_feed(content: bytes) -> list[dict]:
    """Parse un flux et renvoie un item par entrée qui a un lien."""
    feed = feedparser.parse(content)
    if not feed.entries and feed.bozo:
        raise FeedError(f"flux illisible ({feed.bozo_exception})")
    if not feed.entries and not feed.version:
        # page HTML bien formée (bandeau de consentement, défi anti-robot…) servie en 200
        raise FeedError("flux illisible (ni RSS ni Atom)")
    return [item for entry in feed.entries if (item := to_item(entry))]


def to_item(entry: dict) -> dict | None:
    lien = normalize_link(entry.get("link"))
    if not lien:
        return None  # sans lien, pas de clé (source, lien)
    resume_brut = _raw_summary(entry)
    return {
        "lien": lien,
        "titre": clean_text(entry.get("title")),
        "resume": truncate(clean_text(resume_brut)),
        "publie_le": _published_at(entry),
        "rubrique": _rubrique(entry, lien),
        "payload": _payload(entry, resume_brut),
    }


def _raw_summary(entry: dict) -> str:
    # Sans <description>, `entry.summary` renvoie `content:encoded`, c'est-à-dire
    # le texte intégral. `summary_detail` n'existe que si le flux a un vrai extrait.
    detail = entry.get("summary_detail")
    return detail.get("value", "") if detail else ""


def _raw(entry: dict, key: str):
    # dict.get et non entry.get : feedparser remplace sinon un `updated` absent par
    # `published` (et inversement), et le payload ne serait plus « tel que reçu ».
    return dict.get(entry, key)


def _published_at(entry: dict) -> str | None:
    # feedparser ramène ces dates en UTC ; None si absente ou illisible
    parsed = _raw(entry, "published_parsed") or _raw(entry, "updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(timegm(parsed), tz=UTC).isoformat()


def _rubrique(entry: dict, lien: str) -> str | None:
    """La catégorie déclarée par le flux, sinon le premier segment de l'URL."""
    for tag in entry.get("tags", []):
        if term := clean_text(tag.get("term")):
            return term
    for segment in urlsplit(lien).path.split("/"):
        if segment and not segment.isdigit() and "." not in segment:
            return segment
    return None


def _payload(entry: dict, resume_brut: str) -> dict:
    """Les champs autorisés tels que reçus, avant nettoyage."""
    champs = ("id", "title", "link", "published", "updated")
    payload = {key: value for key in champs if (value := _raw(entry, key))}
    if resume_brut:
        payload["summary"] = resume_brut[:MAX_BRUT]
    if tags := [tag["term"] for tag in entry.get("tags", []) if tag.get("term")]:
        payload["tags"] = tags
    return payload
