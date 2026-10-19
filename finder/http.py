"""Cliente HTTP prolijo: pocas consultas, espaciadas, y frena si el sitio pide verificación.

No intenta esquivar protecciones anti-bot: si un portal responde con un desafío,
se corta la consulta a ese portal en esa corrida.
"""
import logging
import random
import time

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}


class Blocked(Exception):
    """El portal pidió verificación (anti-bot) o rechazó la consulta."""


class PoliteSession:
    def __init__(self, min_delay=3.0, max_delay=6.0):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.min_delay, self.max_delay = min_delay, max_delay
        self._last = 0.0

    def get(self, url, **kw):
        wait = self._last + random.uniform(self.min_delay, self.max_delay) - time.time()
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=(10, 25), **kw)
                break
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == 2:
                    raise
                log.info("Conexión cortada (%s); reintento en %ds", e.__class__.__name__, 20 * (attempt + 1))
                time.sleep(20 * (attempt + 1))
            finally:
                self._last = time.time()
        if r.status_code in (202, 403, 429) or "awsWafCookieDomainList" in r.text[:3000]:
            raise Blocked(f"{r.status_code} {url}")
        r.raise_for_status()
        return r
