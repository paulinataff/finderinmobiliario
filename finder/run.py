"""Corrida completa: buscar, completar datos, evaluar, guardar y avisar.

    python -m finder.run                 # chequeo rápido (lo nuevo), manda mail
    python -m finder.run --full          # recorre todos los listados (primera vez / una vez por día)
    python -m finder.run --dry-run       # no manda mail
"""
import argparse
import logging
from pathlib import Path

import requests
import yaml

from . import geo, notify
from .http import Blocked, Gone, PoliteSession
from .rules import Evaluation, evaluate
from .sources import argenprop, mercadolibre
from .store import Store

log = logging.getLogger("finder")
ROOT = Path(__file__).resolve().parent.parent


def collect(cfg, full):
    """Devuelve [(módulo, sesión, avisos)] por portal. Si un portal bloquea, sigue con los demás."""
    out = []
    plans = [
        (mercadolibre, dict(max_pages=40) if full else dict(max_pages=2, today_only=True)),
        (argenprop, dict(max_pages=30 if full else 2)),
    ]
    for mod, kw in plans:
        session = PoliteSession()
        try:
            out.append((mod, session, mod.fetch(session, cfg, **kw)))
        except Blocked as e:
            log.warning("%s pidió verificación anti-bot; lo salteo en esta corrida (%s)", mod.SOURCE, e)
    return out


def same_unit(a, b):
    """Mismo departamento publicado dos veces (otra inmobiliaria u otro portal)."""
    la, lb = a["listing"], b["listing"]
    if None in (la["lat"], lb["lat"], la["m2_cubiertos"], lb["m2_cubiertos"]):
        return False
    near = abs(la["lat"] - lb["lat"]) < 0.0004 and abs(la["lon"] - lb["lon"]) < 0.0005  # ~40 m
    return near and abs(la["m2_cubiertos"] - lb["m2_cubiertos"]) <= 3


def run(full=False, dry_run=False, max_details=60):
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    store = Store()
    fresh = []
    details = 0
    for mod, session, listings in collect(cfg, full):
        blocked = False
        for l in listings:
            if store.seen(l.key):
                continue
            ev = evaluate(l, cfg)
            if ev.reasons:
                # Descartado con los datos del listado: no hace falta leer la ficha.
                store.put(l, ev)
                continue
            if l.lat is None and mod.GEOCODE and l.address:
                coords = geo.geocode(l.address)
                if coords:
                    l.lat, l.lon = coords
                    ev = evaluate(l, cfg)
                    if ev.reasons:
                        store.put(l, ev)
                        continue
            if ev.needs_detail or ev.ok:
                if blocked or details >= max_details:
                    continue  # Queda para la próxima corrida sin marcarlo como visto.
                try:
                    mod.fetch_detail(session, l)
                    details += 1
                except Gone:
                    store.put(l, Evaluation(ok=False, reasons=["aviso dado de baja"]))
                    continue
                except Blocked as e:
                    log.warning("%s bloqueó la ficha; sigo en la próxima corrida (%s)", mod.SOURCE, e)
                    blocked = True
                    continue
                except requests.RequestException as e:
                    log.warning("No pude leer %s (%s)", l.url, e)
                    continue
                if details % 20 == 0:
                    store.save()
                ev = evaluate(l, cfg)
            store.put(l, ev)
            if ev.ok:
                fresh.append(l.key)
                log.info("✔ %s  %s  %s  puntaje %s", l.key, ev.zone, l.address, ev.score)
    store.save()
    geo.save_cache()

    pending = [
        store.get(k) for k in fresh
        if store.get(k)["score"] >= cfg["alertas"]["puntaje_min"] and not store.get(k)["notified"]
    ]
    pending.sort(key=lambda i: -i["score"])
    already = [v for v in store.items.values() if v.get("ok") and v.get("notified")]
    unique = []
    for i in pending:
        if any(same_unit(i, o) for o in already + unique):
            log.info("Duplicado, no se avisa: %s", i["listing"]["url"])
            store.mark_notified(f"{i['listing']['source']}:{i['listing']['id']}")
        else:
            unique.append(i)
    pending = unique
    log.info("%d avisos nuevos que cumplen todo", len(pending))
    if pending and not dry_run:
        notify.send(pending)
        for i in pending:
            store.mark_notified(f"{i['listing']['source']}:{i['listing']['id']}")
        store.save()
    return pending


def send_test(n=5):
    """Manda por mail los mejores n avisos ya encontrados, para probar que las alertas llegan."""
    items = sorted((v for v in Store().items.values() if v["ok"]), key=lambda i: -i["score"])[:n]
    if not items:
        log.info("Todavía no hay avisos que cumplan todo")
        return
    notify.send(items)
    log.info("Mail de prueba enviado con %d avisos", len(items))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-details", type=int, default=60)
    p.add_argument("--test-email", action="store_true", help="manda los mejores avisos encontrados y sale")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.test_email:
        return send_test()
    run(full=a.full, dry_run=a.dry_run, max_details=a.max_details)


if __name__ == "__main__":
    main()
