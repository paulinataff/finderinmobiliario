"""Genera una página HTML con los departamentos que cumplen todo y un mapa de zonas.

    .venv/bin/python scripts/pagina.py salida.html
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).with_name("pagina_template.html")


def main(out):
    state = json.loads((ROOT / "data" / "state.json").read_text())
    avenidas = json.loads((ROOT / "data" / "avenidas.json").read_text())
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    zonas = [{"name": z["nombre"], "rating": z["calificacion"]} for z in cfg["zona"]["microzonas"]]
    items = []
    for v in sorted((v for v in state.values() if v["ok"]), key=lambda v: -v["score"]):
        l = v["listing"]
        items.append({
            "score": v["score"],
            "total": round(v["total_ars"]),
            "price": l["price"],
            "cur": l["currency"],
            "exp": l["expensas"],
            "m2": l["m2_cubiertos"],
            "dorm": l["dormitorios"],
            "amb": l["ambientes"],
            "zone": v["zone"],
            "addr": l["address"].replace(", Capital Federal", "").strip(),
            "title": l["title"],
            "url": l["url"],
            "lat": l["lat"],
            "lon": l["lon"],
            "pileta": v["pileta"],
            "cochera": v["cochera"],
            "age": v.get("antiguedad"),
            "src": l["source"],
            "pub": l["publisher"],
            "seen": v["first_seen"][:10],
        })
    data = {
        "items": items,
        "avenidas": avenidas,
        "zones": zonas,
        "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "evaluated": len(state),
    }
    html = TEMPLATE.read_text().replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    Path(out).write_text(html)
    print(f"{len(items)} departamentos → {out}")


if __name__ == "__main__":
    main(sys.argv[1])
