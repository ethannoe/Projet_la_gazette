"""Journaux structurés : une ligne JSON par événement, sur la sortie standard."""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="seconds"),
            "niveau": record.levelname,
            "message": record.getMessage(),
            **getattr(record, "champs", {}),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure(level: int = logging.INFO) -> None:
    """Journaux JSON sur la sortie standard, à appeler au début de chaque processus.

    Sous Prefect, on garde son handler qui envoie les journaux à l'interface, et on
    retire son affichage console, qui doublerait chaque ligne.
    """
    logger = logging.getLogger("gazette")
    vers_prefect = [h for h in logger.handlers if type(h).__name__ == "APILogHandler"]
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers[:] = [*vers_prefect, handler]
    logger.setLevel(level)
    logger.propagate = False
