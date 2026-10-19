"""Estado entre corridas: qué avisos ya se vieron, cómo se evaluaron y si se avisaron.

Se guarda en un JSON para que en la nube se pueda versionar junto al repo.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "state.json"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=PATH):
        self.path = path
        self.items = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key):
        return self.items.get(key)

    def seen(self, key):
        return key in self.items

    def put(self, listing, ev):
        prev = self.items.get(listing.key, {})
        if not ev.ok:
            # De los descartados alcanza con saber por qué, para no volver a evaluarlos.
            self.items[listing.key] = {
                "first_seen": prev.get("first_seen", now()),
                "ok": False,
                "reasons": ev.reasons,
                "url": listing.url,
            }
            return
        self.items[listing.key] = {
            "first_seen": prev.get("first_seen", now()),
            "notified": prev.get("notified"),
            "ok": ev.ok,
            "score": ev.score,
            "total_ars": ev.total_ars,
            "reasons": ev.reasons,
            "notes": ev.notes,
            "zone": ev.zone,
            "pileta": ev.pileta,
            "cochera": ev.cochera,
            "listing": {k: v for k, v in listing.to_dict().items() if k != "text"},
        }

    def mark_notified(self, key):
        self.items[key]["notified"] = now()

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1, sort_keys=True))
        tmp.replace(self.path)
