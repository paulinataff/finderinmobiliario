"""Vuelve a leer la ficha de los avisos que cumplían todo y los evalúa con los criterios actuales.

Sirve después de cambiar config.yaml o las reglas.

    .venv/bin/python -m scripts.reevaluar
"""
import logging
from pathlib import Path

import requests
import yaml

from finder.http import Blocked, PoliteSession
from finder.model import Listing
from finder.rules import evaluate
from finder.sources import argenprop, mercadolibre
from finder.store import Store

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {"ml": mercadolibre, "ap": argenprop}


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    store = Store()
    sessions = {k: PoliteSession() for k in SOURCES}
    for key, item in list(store.items.items()):
        if not item["ok"]:
            continue
        l = Listing(**item["listing"])
        try:
            SOURCES[l.source].fetch_detail(sessions[l.source], l)
        except (Blocked, requests.RequestException) as e:
            logging.warning("No pude releer %s (%s); queda como estaba", key, e)
            continue
        ev = evaluate(l, cfg)
        store.put(l, ev)
        verdict = f"puntaje {ev.score}" if ev.ok else "descartado: " + ", ".join(ev.reasons)
        logging.info("%s  %s  %s", key, l.address[:40], verdict)
    store.save()


if __name__ == "__main__":
    main()
