"""Geografía: de qué lado de una avenida cae un punto, y geocodificación de direcciones en CABA.

Las avenidas vienen de OpenStreetMap (data/avenidas.json) como listas de tramos [lon, lat].
Para saber de qué lado está un punto se busca el tramo más cercano, se lo orienta en el
sentido "hacia el centro" (de noroeste a sureste) y se mira el signo del producto cruz:
positivo = a la izquierda = lado del río.
"""
import json
import math
import re
from functools import lru_cache
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"

# Sentido general de Santa Fe, Cabildo y Las Heras yendo hacia el centro (lon, lat).
_HEADING = (0.065, -0.03)

# Escala aproximada para convertir grados a metros en Buenos Aires.
_M_PER_DEG_LAT = 111_320
_M_PER_DEG_LON = 111_320 * math.cos(math.radians(-34.59))


@lru_cache(maxsize=None)
def _segments(avenue):
    ways = json.loads((DATA / "avenidas.json").read_text())[avenue]
    segs = []
    for way in ways:
        for a, b in zip(way, way[1:]):
            if (b[0] - a[0]) * _HEADING[0] + (b[1] - a[1]) * _HEADING[1] < 0:
                a, b = b, a
            segs.append((a, b))
    return segs


def _to_m(lon, lat):
    return lon * _M_PER_DEG_LON, lat * _M_PER_DEG_LAT


def side_of(avenue, lat, lon, bounded=False, margin_m=700):
    """Distancia en metros con signo a la avenida: >0 lado del río, <0 lado opuesto.

    Con bounded=True devuelve None si el punto queda más de margin_m metros más allá de
    los extremos de la avenida (por ejemplo, Las Heras termina en Plaza Italia).
    """
    px, py = _to_m(lon, lat)
    best = None
    for a, b in _segments(avenue):
        ax, ay = _to_m(*a)
        bx, by = _to_m(*b)
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy or 1e-9
        t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
        tc = min(1.0, max(0.0, t))
        cx, cy = ax + tc * dx, ay + tc * dy
        dist = math.hypot(px - cx, py - cy)
        if best is None or dist < best[0]:
            cross = dx * (py - ay) - dy * (px - ax)
            best = (dist, cross, t, (a, b))
    dist, cross, _, _ = best
    if bounded:
        lo, hi = _extent(avenue)
        if not lo - margin_m <= _proj((lon, lat)) <= hi + margin_m:
            return None
    return dist if cross > 0 else -dist


@lru_cache(maxsize=None)
def _extent(avenue):
    """Rango de la avenida medido sobre el sentido general (para saber dónde termina)."""
    proj = [_proj(p) for s in _segments(avenue) for p in s]
    return min(proj), max(proj)


def _proj(p):
    """Posición en metros de un punto (lon, lat) a lo largo del sentido general."""
    x, y = _to_m(*p)
    hx, hy = _to_m(*_HEADING)
    n = math.hypot(hx, hy)
    return (x * hx + y * hy) / n


_STRIP = re.compile(r"\b(piso|p\.|dto|depto|departamento|unidad|uf)\b.*$", re.I)


_CACHE_PATH = DATA / "geocache.json"
_cache = None
_failures = 0


def _load_cache():
    global _cache
    if _cache is None:
        _cache = json.loads(_CACHE_PATH.read_text()) if _CACHE_PATH.exists() else {}
    return _cache


def save_cache():
    if _cache is not None:
        _CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=0, sort_keys=True))


def _clean(address):
    q = _STRIP.sub("", (address or "").split(",")[0])
    q = re.sub(r"\bal\b", " ", q, flags=re.I)
    return re.sub(r"\s+", " ", q).strip()


def geocode(address):
    """Geocodifica una dirección de CABA con el normalizador oficial de la Ciudad (USIG).

    Guarda los resultados en data/geocache.json. Si el servicio falla 3 veces seguidas,
    deja de consultarlo en esta corrida (los avisos quedan para leer la ficha).
    """
    global _failures
    q = _clean(address)
    if not re.search(r"\d", q):
        return None
    cache = _load_cache()
    if q in cache:
        return tuple(cache[q]) if cache[q] else None
    if _failures >= 3:
        return None
    try:
        r = requests.get(
            "https://servicios.usig.buenosaires.gob.ar/normalizar/",
            params={"direccion": q, "geocodificar": "TRUE", "srid": "4326"},
            timeout=5,
        )
        result = None
        for d in r.json().get("direccionesNormalizadas", []):
            c = d.get("coordenadas")
            if c and d["direccion"].endswith("CABA"):
                result = (float(c["y"]), float(c["x"]))
                break
        _failures = 0
        cache[q] = result
        return result
    except (requests.RequestException, ValueError):
        _failures += 1
        return None
