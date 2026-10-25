"""MercadoLibre Inmuebles: listado filtrado por barrio y superficie, y ficha de cada aviso."""
import json
import logging
import re

import requests

from ..http import Blocked, Gone
from ..model import Listing

log = logging.getLogger(__name__)

SOURCE = "ml"
# La ficha trae coordenadas: no hace falta geocodificar la dirección.
GEOCODE = False
BASE = "https://inmuebles.mercadolibre.com.ar/departamentos/alquiler/capital-federal/"
PAGE_SIZE = 48


def _state(html):
    i = html.find("_n.ctx.r=")
    if i < 0:
        return {}
    data, _ = json.JSONDecoder().raw_decode(html, i + len("_n.ctx.r="))
    return data


def _walk(o, key):
    """Todos los valores de `key` en cualquier nivel del JSON."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            yield from _walk(v, key)
    elif isinstance(o, list):
        for x in o:
            yield from _walk(x, key)


def _num(text):
    m = re.search(r"\d[\d\.]*(?:,\d+)?", text or "")
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def list_url(cfg, page=0, today_only=False):
    barrios = "-o-".join(cfg["zona"]["barrios"])
    m2 = cfg["requisitos"]["m2_cubiertos_min"]
    parts = []
    if page:
        parts.append(f"_Desde_{page * PAGE_SIZE + 1}")
    if today_only:
        parts.append("_PublishedToday_YES")
    parts.append(f"_COVERED*AREA_{m2}m%C2%B2-*_NoIndex_True")
    return f"{BASE}{barrios}/{''.join(parts)}"


def parse_list(html):
    out = []
    for card in _walk(_state(html), "polycard"):
        meta = card.get("metadata", {})
        comps = {c.get("type"): c for c in card.get("components", [])}
        price = comps.get("price", {}).get("price", {}).get("current_price", {})
        attrs = comps.get("attributes_list", {}).get("attributes_list", {}).get("texts", [])
        l = Listing(
            source=SOURCE,
            id=meta.get("id", ""),
            url="https://" + meta.get("url", "").split("#")[0],
            title=comps.get("title", {}).get("title", {}).get("text", ""),
            address=comps.get("location", {}).get("location", {}).get("text", ""),
            price=price.get("value"),
            currency=price.get("currency", "ARS"),
            publisher=re.sub(r"\s*\{.*?\}", "", comps.get("seller", {}).get("seller", {}).get("text", "")),
            images=[
                f"https://http2.mlstatic.com/D_NQ_NP_{p['id']}-O.webp"
                for p in card.get("pictures", {}).get("pictures", [])[:1]
            ],
        )
        for a in attrs:
            if "dorm" in a:
                l.dormitorios = int(_num(a))
            elif "amb" in a:
                l.ambientes = int(_num(a))
            elif "cubierto" in a:
                l.m2_cubiertos = _num(a)
        if l.id:
            out.append(l)
    return out


def parse_detail(html, l):
    # Un aviso dado de baja sigue mostrando sus datos, con el cartel "Publicación finalizada".
    if re.search(r"\"item_status\":\"(closed|paused|inactive)\"|-inactive-", html):
        raise Gone(l.url)
    st = _state(html)
    specs = {}
    for groups in _walk(st, "specs"):
        for g in groups if isinstance(groups, list) else []:
            for a in g.get("attributes", []):
                specs[a.get("id", "")] = a.get("text", "")
    if not specs:
        # Página sin los datos del aviso (verificación o error temporal): no evaluar con eso.
        raise Blocked(f"ficha sin datos {l.url}")
    loc = next((v for v in _walk(st, "map_info") if isinstance(v, dict)), {}).get("location", {})
    if loc.get("latitude"):
        l.lat, l.lon = float(loc["latitude"]), float(loc["longitude"])
    desc = next((v for v in _walk(st, "content") if isinstance(v, str) and len(v) > 40), "")
    if specs.get("Superficie cubierta"):
        l.m2_cubiertos = _num(specs["Superficie cubierta"])
    if specs.get("Dormitorios"):
        l.dormitorios = int(_num(specs["Dormitorios"]))
    if specs.get("Ambientes"):
        l.ambientes = int(_num(specs["Ambientes"]))
    if specs.get("Cocheras") is not None and _num(specs.get("Cocheras")) is not None:
        l.cocheras = int(_num(specs["Cocheras"]))
    exp = specs.get("Expensas")
    if exp:
        l.expensas = _num(exp)
        l.expensas_currency = "USD" if "USD" in exp else "ARS"
    spec_text = " · ".join(f"{k}: {v}" for k, v in specs.items())
    l.text = f"{l.title}\n{spec_text}\n{desc}"
    l.detailed = True
    return l


def fetch(session, cfg, max_pages=1, today_only=False):
    """Recorre el listado. Con today_only solo trae lo publicado hoy (para chequeos frecuentes)."""
    seen, out = set(), []
    for page in range(max_pages):
        try:
            items = parse_list(session.get(list_url(cfg, page, today_only)).text)
        except requests.RequestException as e:
            log.warning("MercadoLibre: corto en la página %d (%s)", page + 1, e)
            break
        
        new = []
        for l in items:
            if l.id not in seen:
                seen.add(l.id)
                new.append(l)
        log.info("MercadoLibre: página %d, %d avisos", page + 1, len(new))
        if not new:
            break
        out.extend(new)
        if len(new) < PAGE_SIZE:
            break
    log.info("MercadoLibre: %d avisos en el listado", len(out))
    return out


def fetch_detail(session, l):
    r = session.get(l.url)
    # Un aviso dado de baja redirige al listado o muestra "Publicación finalizada".
    if "departamento.mercadolibre" not in r.url:
        raise Gone(l.url)
    return parse_detail(r.text, l)
