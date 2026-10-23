"""Alerte vers le canal de l'équipe : un webhook Discord ou Slack (GAZETTE_ALERTE_WEBHOOK)."""

import logging

import requests

from gazette.fetch import USER_AGENT

log = logging.getLogger("gazette.alertes")


def envoyer(message: str, url: str | None) -> bool:
    """Poste le message sur le webhook ; renvoie True s'il est parti."""
    if not url:
        log.warning("alerte non envoyée, GAZETTE_ALERTE_WEBHOOK n'est pas défini : %s", message)
        return False
    if "discord" in url:
        corps = {"content": message[:1900]}  # Discord refuse plus de 2 000 caractères
    elif "slack" in url:
        corps = {"text": message}
    else:
        corps = {"content": message[:1900], "text": message}
    try:
        reponse = requests.post(url, json=corps, headers={"User-Agent": USER_AGENT}, timeout=10)
        reponse.raise_for_status()
    except requests.RequestException as exc:
        log.error("alerte non envoyée, le webhook a échoué : %s", type(exc).__name__)
        return False
    log.info("alerte envoyée", extra={"champs": {"evenement": "alerte", "message": message}})
    return True
