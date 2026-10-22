"""Réglages lus dans l'environnement (fixés par docker-compose.yml)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    articles_dir: str
    sources_file: str
    intervalle_min: int  # un passage toutes les N minutes
    delai_min: int  # jamais deux requêtes à une même source à moins de N minutes


def load() -> Config:
    return Config(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://gazette:gazette@localhost:5432/gazette"
        ),
        articles_dir=os.environ.get("GAZETTE_ARTICLES_DIR", "articles_bruts"),
        sources_file=os.environ.get("GAZETTE_SOURCES_FILE", "sources.csv"),
        intervalle_min=int(os.environ.get("GAZETTE_INTERVALLE_MIN", "30")),
        delai_min=int(os.environ.get("GAZETTE_DELAI_MIN", "10")),
    )
