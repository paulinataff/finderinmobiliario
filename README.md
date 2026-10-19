# Finder inmobiliario

Busca departamentos en alquiler en MercadoLibre y Argenprop, se queda con los que cumplen
los criterios de `config.yaml`, les asigna un puntaje y avisa por email.

## Cómo decide

1. **Listado**: trae los avisos de Palermo, Recoleta y Las Cañitas (con 1 dormitorio o más y 38 m² o más cuando el portal permite filtrarlo).
2. **Ubicación**: usa las coordenadas del aviso o geocodifica la dirección con el normalizador oficial de la Ciudad (USIG), y calcula de qué lado de Av. Santa Fe/Cabildo y de Av. Las Heras cae (trazado de OpenStreetMap en `data/avenidas.json`).
3. **Excluyentes**: alquiler + expensas ≤ $1.300.000 ($1.400.000 si tiene cochera incluida; los avisos en dólares se pasan a pesos con el dólar MEP), 1 dormitorio o más, 38 m² cubiertos o más, balcón y estar del lado del río de Santa Fe.
4. **Puntaje** (0–100): zona (pasando Las Heras suma más), pileta, cochera, precio y superficie.
5. **Alerta**: un mail con los avisos nuevos, ordenados por puntaje.

Los portales se consultan despacio. Si alguno pide verificación anti-bot, esa corrida lo saltea: no se intenta esquivar.

## Uso local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m finder.run --full --dry-run   # primera recorrida, sin mandar mail
.venv/bin/python -m finder.run                    # chequeo rápido + mail
```

## En la nube (GitHub Actions)

`.github/workflows/buscar.yml` corre un chequeo cada 30 minutos y una recorrida completa por día.
Hay que cargar estos secrets en el repo: `SMTP_USER`, `SMTP_PASSWORD` (contraseña de aplicación de Gmail) y `ALERT_TO`.
El estado (qué avisos ya se vieron) queda en `data/state.json`.
