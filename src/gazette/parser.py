"""Transforme un flux RSS ou Atom en items : titre, extrait, lien, date, source.

On ne garde que ces cinq champs (cf. docs/cadrage.md) : ni texte intégral
(`content:encoded`), ni auteur, ni image.
"""

import html
import re
from calendar import timegm
from datetime import UTC, datetime

import feedparser

MAX_SUMMARY = 500  # au-delà, ce n'est plus un extrait

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


class FeedError(ValueError):
    """Le contenu reçu n'est pas un flux lisible."""


def clean_text(value: str | None) -> str:
    """Retire les balises HTML, décode les entités et normalise les espaces."""
    text = html.unescape(_TAG.sub(" ", value or ""))
    return _SPACES.sub(" ", text).strip()


def truncate(text: str, limit: int = MAX_SUMMARY) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def parse_feed(content: bytes, source: str) -> list[dict]:
    """Parse un flux et renvoie ses items valides, sans doublon d'URL."""
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise FeedError(f"{source} : flux illisible ({feed.bozo_exception})")

    items, seen = [], set()
    for entry in feed.entries:
        item = _to_item(entry, source)
        if item is None or item["url"] in seen:
            continue
        seen.add(item["url"])
        items.append(item)
    return items


def _to_item(entry: dict, source: str) -> dict | None:
    title = clean_text(entry.get("title"))
    url = (entry.get("link") or "").strip()
    # feedparser ramène déjà ces dates en UTC
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if not title or not url or published is None:
        return None
    return {
        "source": source,
        "title": title,
        "summary": truncate(clean_text(_summary(entry))),
        "url": url,
        "published_at": datetime.fromtimestamp(timegm(published), tz=UTC).isoformat(),
    }


def _summary(entry: dict) -> str:
    # Sans <description>, `entry.summary` renvoie `content:encoded`, c'est-à-dire
    # le texte intégral. `summary_detail` n'existe que si le flux a un vrai extrait.
    detail = entry.get("summary_detail")
    return detail.get("value", "") if detail else ""
