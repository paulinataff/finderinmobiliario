"""Vuelve a leer la ficha de los avisos que cumplían todo y los evalúa con los criterios actuales.

Sirve después de cambiar config.yaml o las reglas.

    .venv/bin/python -m scripts.reevaluar
"""
import logging
from pathlib import Path

import requests
import yaml

from finder.http import Blocked, Gone, PoliteSession
from finder.model import Listing
from finder.rules import Evaluation, evaluate
from finder.sources import argenprop, mercadolibre
from finder.store import Store

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {"ml": mercadolibre, "ap": argenprop}


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    store = Store()
    sessions = {k: PoliteSession() for k in SOURCES}
    pending = [k for k, v in store.items.items() if v["ok"]]
    for attempt in range(2):
        retry = []
        for key in pending:
            if reevaluate(store, cfg, key, sessions):
                continue
            retry.append(key)
        # Las fichas que llegaron sin datos se reintentan con una sesión nueva.
        pending = retry
        sessions = {k: PoliteSession() for k in SOURCES}
    store.save()


def reevaluate(store, cfg, key, sessions):
    """Devuelve False si la ficha no se pudo leer y conviene reintentar."""
    l = Listing(**store.get(key)["listing"])
    try:
        SOURCES[l.source].fetch_detail(sessions[l.source], l)
    except Gone:
        store.put(l, Evaluation(ok=False, reasons=["aviso dado de baja"]))
        logging.info("%s  %s  dado de baja", key, l.address[:40])
        return True
    except (Blocked, requests.RequestException) as e:
        logging.warning("No pude releer %s (%s); queda como estaba", key, e)
        return False
    ev = evaluate(l, cfg)
    store.put(l, ev)
    verdict = f"puntaje {ev.score}" if ev.ok else "descartado: " + ", ".join(ev.reasons)
    logging.info("%s  %s  %s", key, l.address[:40], verdict)
    return True


if __name__ == "__main__":
    main()
