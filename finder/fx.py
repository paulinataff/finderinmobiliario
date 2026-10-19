import logging
from functools import lru_cache

import requests

log = logging.getLogger(__name__)

_FALLBACK = 1550.0


@lru_cache(maxsize=None)
def usd_to_ars(casa="bolsa"):
    """Precio de venta del dólar según dolarapi.com (oficial, blue, bolsa = MEP)."""
    try:
        r = requests.get(f"https://dolarapi.com/v1/dolares/{casa}", timeout=15)
        return float(r.json()["venta"])
    except (requests.RequestException, KeyError, ValueError):
        log.warning("No pude obtener la cotización del dólar; uso %s", _FALLBACK)
        return _FALLBACK


def to_ars(amount, currency, casa="bolsa"):
    if amount is None:
        return None
    return amount * usd_to_ars(casa) if currency == "USD" else amount
