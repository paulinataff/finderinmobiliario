"""Requisitos excluyentes y puntaje de cada aviso."""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from . import geo
from .fx import to_ars


def _norm(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return text.lower()


def _structured(text, label):
    """Lee campos tipo 'Pileta: Sí' / 'Pileta: No' de las características del aviso."""
    m = re.search(rf"\b{label}\s*:\s*(si|no)\b", text)
    return None if not m else m.group(1) == "si"


def has_balcon(text):
    t = _norm(text)
    if re.search(r"superficie de balcon\s*:\s*[1-9]", t) or re.search(r"tipo de balcon\s*:", t):
        return True
    if re.search(r"superficie de balcon\s*:\s*0\b", t):
        return False
    s = _structured(t, "balcon")
    if s is not None:
        return s
    if re.search(r"\b(sin|no tiene|no posee|no cuenta con)\s+balcon", t):
        return False
    # Un balcón francés es solo una baranda: no cuenta.
    return True if re.search(r"balcon(?!\s+frances)", t) else None


def has_pileta(text):
    t = _norm(text)
    for label in ("pileta", "piscina"):
        s = _structured(t, label)
        if s is not None:
            return s
    if re.search(r"\b(sin|no tiene)\s+(pileta|piscina)", t):
        return False
    return True if re.search(r"\b(pileta|piscina|natatorio)\b", t) else None


def antiguedad(text):
    """Años del edificio según el aviso; 0 si es a estrenar, None si no lo dice."""
    t = _norm(text)
    if re.search(r"a estrenar|antiguedad\s*:?\s*\|?\s*(a estrenar|0\b|en construccion)", t):
        return 0
    m = re.search(r"antiguedad\s*:?\s*\|?\s*(\d{1,3})", t)
    return int(m.group(1)) if m else None


def es_monoambiente(l, ambientes_min=2):
    if l.ambientes is not None:
        return l.ambientes < ambientes_min
    return bool(re.search(r"\bmono\s?ambiente\b", _norm(l.title)))


def microzona(lat, lon, zonas):
    kx = 0.82  # cos(latitud de Buenos Aires): los grados de longitud son más cortos
    return min(zonas, key=lambda z: (lat - z["lat"]) ** 2 + ((lon - z["lon"]) * kx) ** 2)


def cochera_incluida(l):
    t = _norm(l.text)
    extra = re.search(r"cochera\s+(opcional|aparte|adicional|por separado|a convenir|con costo)", t)
    if l.cocheras is not None:
        return l.cocheras > 0 and not extra
    if re.search(r"\b(sin|no tiene)\s+cochera", t) or extra:
        return False
    return True if re.search(r"\b(con|incluye|y)\s+cochera\b", t) else None


@dataclass
class Evaluation:
    ok: bool
    score: int = 0
    total_ars: Optional[float] = None
    reasons: List[str] = field(default_factory=list)  # Por qué se descartó
    notes: List[str] = field(default_factory=list)  # Cosas a tener en cuenta
    zone: str = ""
    balcon: Optional[bool] = None
    pileta: Optional[bool] = None
    cochera: Optional[bool] = None
    antiguedad: Optional[int] = None
    # Falta información que solo está en la ficha del aviso.
    needs_detail: bool = False


def evaluate(l, cfg):
    req, pres, pts = cfg["requisitos"], cfg["presupuesto"], cfg["puntaje"]
    ev = Evaluation(ok=True)
    casa = pres.get("dolar", "bolsa")

    ev.balcon = has_balcon(l.text)
    ev.pileta = has_pileta(l.text)
    ev.cochera = cochera_incluida(l)

    price = to_ars(l.price, l.currency, casa)
    exp = to_ars(l.expensas, l.expensas_currency, casa)
    cap = pres["maximo_con_cochera"] if ev.cochera else pres["maximo"]
    if price is None:
        ev.reasons.append("sin precio")
    else:
        ev.total_ars = price + (exp or 0)
        if ev.total_ars > pres["maximo_con_cochera"] or (ev.cochera is False and ev.total_ars > cap):
            ev.reasons.append(f"total ${ev.total_ars:,.0f} supera el máximo".replace(",", "."))
        elif ev.total_ars > cap:
            if ev.cochera is None and not l.detailed:
                ev.needs_detail = True
            else:
                ev.reasons.append(f"total ${ev.total_ars:,.0f} supera el máximo".replace(",", "."))
        if exp is None:
            ev.needs_detail = ev.needs_detail or not l.detailed
            ev.notes.append("no informa expensas")

    if es_monoambiente(l, req.get("ambientes_min", 2)):
        ev.reasons.append("monoambiente")
    if l.dormitorios is not None and l.dormitorios < req["dormitorios_min"]:
        ev.reasons.append(f"{l.dormitorios} dormitorios")
    elif l.dormitorios is None:
        ev.needs_detail = True
    if l.m2_cubiertos is not None and l.m2_cubiertos < req["m2_cubiertos_min"]:
        ev.reasons.append(f"{l.m2_cubiertos:.0f} m² cubiertos")
    elif l.m2_cubiertos is None:
        ev.needs_detail = True

    if req.get("balcon"):
        if ev.balcon is False:
            ev.reasons.append("sin balcón")
        elif ev.balcon is None:
            if l.detailed:
                ev.reasons.append("no menciona balcón")
            else:
                ev.needs_detail = True

    if l.lat is None:
        if l.detailed:
            ev.reasons.append("sin ubicación")
        else:
            ev.needs_detail = True
    else:
        sf = geo.side_of("santa_fe", l.lat, l.lon)
        if sf < cfg["zona"]["santa_fe_min_m"]:
            ev.reasons.append(f"del otro lado de Santa Fe ({-sf:.0f} m)")
        else:
            z = microzona(l.lat, l.lon, cfg["zona"]["microzonas"])
            ev.zone = z["nombre"]
            if z.get("descartar"):
                ev.reasons.append(f"zona descartada ({z['nombre']})")
            zpts = pts["zona"] * z["calificacion"] / 10
            ev.score += zpts

    if ev.reasons:
        ev.ok = False
        return ev

    if ev.pileta:
        ev.score += pts["pileta"]
    if ev.cochera:
        ev.score += pts["cochera"]
    if ev.total_ars is not None:
        # Puntaje completo al estar 30% o más por debajo del máximo.
        ev.score += round(pts["precio"] * min(1.0, max(0.0, 1 - ev.total_ars / cap) / 0.3))
    if l.m2_cubiertos:
        span = max(1, pts["m2_ideal"] - req["m2_cubiertos_min"])
        frac = min(1.0, (l.m2_cubiertos - req["m2_cubiertos_min"]) / span)
        ev.score += round(pts["superficie"] * frac)
    ev.antiguedad = antiguedad(l.text)
    if ev.antiguedad is not None:
        span = max(1, pts["antiguedad_max"] - pts["antiguedad_ideal"])
        frac = 1 - min(1.0, max(0.0, (ev.antiguedad - pts["antiguedad_ideal"]) / span))
        ev.score += pts["antiguedad"] * frac
    if l.expensas is None:
        ev.score += pts["sin_expensas"]
    best = pts["zona"] + pts["pileta"] + pts["cochera"] + pts["precio"] + pts["superficie"] + pts["antiguedad"]
    ev.score = max(0, min(100, round(100 * ev.score / best)))
    return ev
