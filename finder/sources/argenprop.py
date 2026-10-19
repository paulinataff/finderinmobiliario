"""Argenprop: listado ordenado por más nuevos y ficha de cada aviso."""
import logging
import re

import requests
from bs4 import BeautifulSoup

from ..http import Blocked
from ..model import Listing

log = logging.getLogger(__name__)

SOURCE = "ap"
# Geocodificar evita pedir la ficha (Argenprop limita bastante las consultas).
GEOCODE = True
BASE = "https://www.argenprop.com"


def _num(text):
    m = re.search(r"\d[\d\.]*(?:,\d+)?", text or "")
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def list_url(cfg, page=1):
    barrios = "-o-".join(cfg["zona"]["barrios"])
    dmin = cfg["requisitos"]["dormitorios_min"]
    dorms = "-o-".join(
        f"{n}-dormitorio" if n == 1 else f"{n}-dormitorios" for n in range(dmin, 5)
    )
    url = f"{BASE}/departamentos/alquiler/{barrios}/{dorms}?orden-masnuevos"
    return url + (f"&pagina-{page}" if page > 1 else "")


def parse_list(html):
    out = []
    for item in BeautifulSoup(html, "lxml").select("a.card[idaviso]"):
        currency = "USD" if item.get("idmoneda") == "2" else "ARS"
        l = Listing(
            source=SOURCE,
            id=item["idaviso"],
            url=BASE + item["href"],
            price=_num(item.get("montooperacion")),
            currency=currency,
        )
        if item.get("dormitorios"):
            l.dormitorios = int(item["dormitorios"])
        addr = item.select_one(".card__address")
        l.address = addr.get_text(" ", strip=True) if addr else ""
        exp = item.select_one(".card__expenses")
        if exp:
            l.expensas = _num(exp.get_text())
            l.expensas_currency = "USD" if "USD" in exp.get_text() else "ARS"
        for li in item.select(".card__main-features li"):
            t = li.get_text(" ", strip=True)
            if "cubie" in t and "semi" not in t.lower():
                l.m2_cubiertos = _num(t)
            elif "dorm" in t and l.dormitorios is None:
                l.dormitorios = int(_num(t))
            elif "ambiente" in t:
                l.ambientes = int(_num(t))
        title = item.select_one(".card__title")
        info = item.select_one(".card__info")
        l.title = title.get_text(" ", strip=True) if title else ""
        l.text = f"{l.title}\n{info.get_text(' ', strip=True) if info else ''}"
        img = item.select_one(".card__photos img")
        if img:
            l.images = [img.get("src") or img.get("data-src")]
        out.append(l)
    return out


def parse_detail(html, l):
    b = BeautifulSoup(html, "lxml")
    m = b.select_one("[data-latitude]")
    if m:
        try:
            l.lat = float(m["data-latitude"].replace(",", "."))
            l.lon = float(m["data-longitude"].replace(",", "."))
        except ValueError:
            pass
    feats = [s.get_text(" | ", strip=True) for s in b.select(".property-main-features, .property-features")]
    desc = b.select_one(".section-description--content")
    text = "\n".join(feats)
    for row in b.select(".property-features li"):
        t = row.get_text(" ", strip=True)
        if t.lower().startswith("sup. cubierta"):
            l.m2_cubiertos = _num(t)
        elif t.lower().startswith("cant. dormitorios"):
            l.dormitorios = int(_num(t))
        elif t.lower().startswith("cant. cocheras") or t.lower().startswith("cocheras"):
            l.cocheras = int(_num(t) or 0)
        elif t.lower().startswith("expensas") and _num(t):
            l.expensas = _num(t)
    l.text = f"{l.title}\n{text}\n{desc.get_text(' ', strip=True) if desc else ''}"
    l.detailed = True
    return l


def fetch(session, cfg, max_pages=1):
    out = []
    for page in range(1, max_pages + 1):
        try:
            items = parse_list(session.get(list_url(cfg, page)).text)
        except Blocked:
            if not out:
                raise
            log.warning("Argenprop pidió verificación en la página %d; sigo con lo que hay", page)
            break
        except requests.RequestException as e:
            log.warning("Argenprop: corto en la página %d (%s)", page, e)
            break
        log.info("Argenprop: página %d, %d avisos", page, len(items))
        out.extend(items)
        if len(items) < 20:
            break
    log.info("Argenprop: %d avisos en el listado", len(out))
    return out


def fetch_detail(session, l):
    return parse_detail(session.get(l.url).text, l)
