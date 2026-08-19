# 🍳 Recetas desde Instagram

Compartes un reel de cocina desde el iPhone y, un par de minutos después:

- la **receta paso a paso** está en una web pensada para leer en la tablet
  mientras cocinas, y
- los **ingredientes con sus cantidades** están en tu lista de la compra de
  Recordatorios.

No hay que instalar ninguna app en el iPhone: se usa **Atajos**, que ya viene
con iOS, más un pequeño servidor propio.

```
Instagram → Compartir → Atajo «Guardar receta»
                            │
                            ▼
              tu servidor (esta aplicación)
       yt-dlp → ffmpeg → Whisper → Claude Opus 5
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
   web para la tablet            lista de la compra
   (modo cocina)                 → Recordatorios (iPhone)
```

## Cómo saca la receta

De cada vídeo se aprovechan tres fuentes a la vez, porque ninguna basta por sí
sola:

1. **El pie del post** — casi siempre trae la lista de ingredientes con cantidades.
2. **El audio**, transcrito con Whisper — el orden real de los pasos y las técnicas.
3. **Fotogramas del vídeo** — Claude los lee para pillar las cantidades que
   aparecen sobreimpresas en pantalla y que no están en ningún texto.

Con eso, Claude Opus 5 devuelve una receta estructurada (ingredientes con
cantidad, unidad y sección del supermercado; pasos autocontenidos con tiempos y
temporizadores) validada contra un esquema fijo. Lo que ha tenido que deducir
queda anotado en la ficha, así que sabes de qué fiarte.

## Puesta en marcha

```bash
cp .env.example .env      # rellena ANTHROPIC_API_KEY, API_KEY y APP_PASSWORD
docker compose up -d --build
curl http://localhost:8000/healthz
```

Después:

1. **[docs/despliegue.md](docs/despliegue.md)** — ponerlo en Internet con HTTPS,
   cookies de Instagram, coste por receta y copias de seguridad.
2. **[docs/atajo-ios.md](docs/atajo-ios.md)** — montar el Atajo paso a paso
   (es lo que hace que todo sea cómodo de usar).

## La web de cocina

- **Modo cocina**: un paso por pantalla, letra grande, temporizadores con
  aviso sonoro y **la pantalla no se apaga** mientras estás en él.
- Se avanza tocando, deslizando o con las flechas del teclado.
- Los ingredientes y los pasos se marcan con casillas que se recuerdan en el
  propio dispositivo.
- Selector de raciones: reescala todas las cantidades, y la lista de la compra
  sale ya escalada.
- Añádela a la pantalla de inicio de la tablet y se comporta como una app.

## API

Todas las rutas `/api/*` piden la clave en la cabecera `X-API-Key`
(o `?key=…`, que es más fácil de usar desde Atajos).

| Método | Ruta | Para qué |
|---|---|---|
| `POST` | `/api/recipes` | `{"url": "...", "wait": 0, "force": false}` → encola el vídeo |
| `GET` | `/api/recipes` | Lista de recetas (`?q=` busca) |
| `GET` | `/api/recipes/{id}` | Estado y receta completa |
| `GET` | `/api/recipes/{id}/shopping-list` | Lista de la compra (`?format=text`, `?servings=4`…) |
| `POST` | `/api/recipes/{id}/retry` | Reintentar una que falló |
| `DELETE` | `/api/recipes/{id}` | Borrarla |
| `GET` | `/healthz` | Estado del servicio (sin clave) |

Los parámetros de la lista de la compra están detallados en
[docs/atajo-ios.md](docs/atajo-ios.md#ajustes-útiles-de-la-lista-de-la-compra).

Ejemplo:

```bash
curl -X POST https://recetas.tudominio.com/api/recipes \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://www.instagram.com/reel/XXXX/", "wait": 120}'
```

## Desde la terminal

```bash
python -m app.cli "https://www.instagram.com/reel/XXXX/"
python -m app.cli "https://www.instagram.com/reel/XXXX/" --json --raciones 4
```

## Estructura

```
app/
├── main.py            API + páginas web
├── models.py          receta, ingredientes y esquema JSON del modelo
├── shopping.py        construcción de la lista de la compra
├── db.py              SQLite
├── security.py        clave de API y sesión web
├── cli.py             procesar una URL desde la terminal
├── pipeline/
│   ├── download.py    yt-dlp: vídeo + pie del post
│   ├── media.py       ffmpeg: fotogramas y audio
│   ├── transcribe.py  Whisper (opcional)
│   ├── extract.py     Claude: vídeo → receta estructurada
│   └── runner.py      orquestación y estados
├── templates/         web (Jinja2)
└── static/            estilos y modo cocina
docs/                  despliegue y Atajo de iOS
tests/                 pytest
```

## Desarrollo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

## Notas y límites

- **Instagram exige sesión** para bastantes reels: hay que configurar cookies
  (ver [docs/despliegue.md](docs/despliegue.md#4-cookies-de-instagram)). Es la
  causa más habitual de que falle una receta.
- **Uso personal.** Descarga vídeos de terceros para tu propio consumo; no
  publiques las recetas resultantes como si fueran tuyas ni las redistribuyas.
- **Repasa las cantidades** en recetas de repostería antes de fiarte: si el
  vídeo no las dice, el modelo las estima, y lo avisa en la ficha con la
  confianza y las advertencias.
