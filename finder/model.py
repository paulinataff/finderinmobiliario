from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class Listing:
    source: str
    id: str
    url: str
    title: str = ""
    address: str = ""
    barrio: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    price: Optional[float] = None
    currency: str = "ARS"
    expensas: Optional[float] = None
    expensas_currency: str = "ARS"
    m2_cubiertos: Optional[float] = None
    dormitorios: Optional[int] = None
    ambientes: Optional[int] = None
    cocheras: Optional[int] = None
    # Texto libre (título, descripción, características) para detectar balcón, pileta, etc.
    text: str = ""
    images: List[str] = field(default_factory=list)
    publisher: str = ""
    # True cuando ya se leyó la ficha completa del aviso.
    detailed: bool = False

    @property
    def key(self):
        return f"{self.source}:{self.id}"

    def to_dict(self):
        return asdict(self)
