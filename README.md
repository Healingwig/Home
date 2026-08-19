# 🍳 Recetas desde Instagram

Compartes un reel de cocina desde el iPhone y, al minuto:

- la **receta paso a paso** está en una web pensada para leer en la tablet
  mientras cocinas, y
- los **ingredientes con sus cantidades** están en tu lista de la compra de
  Recordatorios.

No hay que instalar ninguna app (se usa **Atajos**, que ya viene con iOS), no
hay que tener ningún ordenador encendido y **se puede usar sin pagar nada**:
todo cabe en las capas gratuitas de Cloud Run, Cloud Storage y Gemini.

```
iPhone: Instagram → Compartir → Atajo «Guardar receta»
                            │
                            ▼
            Cloud Run (se enciende y se apaga solo)
              yt-dlp → ffmpeg → Gemini
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
   web para la tablet            lista de la compra
   (modo cocina)                 → Recordatorios (iPhone)
```

## Cómo saca la receta

Un reel reparte la información entre tres sitios y ninguno basta por sí solo:
el pie del post (cantidades), lo que dice la persona (orden y técnica) y el
**texto sobreimpreso en el vídeo**, que no está escrito en ningún lado.

Por eso se le manda a Gemini **el vídeo entero**, recomprimido para que quepa en
una petición: lo ve y lo escucha en la misma pasada, junto con el pie del post.
Devuelve una receta estructurada —ingredientes con cantidad, unidad y sección
del supermercado; pasos autocontenidos con tiempos y temporizadores— validada
contra un esquema fijo. Lo que ha tenido que deducir queda anotado en la ficha
con un nivel de confianza, así que sabes de qué fiarte.

## Qué modelo usa

Es intercambiable con una variable del `.env`:

| `LLM_PROVIDER` | Coste | Dónde corre | Notas |
|---|---|---|---|
| `gemini` *(por defecto)* | **Gratis** | Cloud Run o tu equipo | Recibe el vídeo con su audio |
| `ollama` | **Gratis** | Un equipo tuyo con 8–16 GB de RAM | Nada sale de tu casa |
| `anthropic` | ~0,15 €/receta | Donde sea | La mejor lectura del texto sobreimpreso |

Con `ollama` y `anthropic` se usa el modo de reserva: fotogramas extraídos con
ffmpeg y audio transcrito en local con Whisper.

## Puesta en marcha

El despliegue completo está en **[docs/despliegue.md](docs/despliegue.md)**; en
resumen:

```bash
gcloud storage buckets create gs://recetas-$USER --location=us-central1
gcloud run deploy recetas --source . --region us-central1 --allow-unauthenticated \
  --timeout 300 --memory 1Gi \
  --set-env-vars "STORAGE_BACKEND=gcs,GCS_BUCKET=recetas-$USER,GEMINI_API_KEY=...,API_KEY=...,APP_PASSWORD=..."
```

Te devuelve una URL con HTTPS. Después, **[docs/atajo-ios.md](docs/atajo-ios.md)**
para montar el Atajo (son siete acciones).

¿Prefieres no dar una tarjeta a Google? Corre igual en tu equipo con
`docker compose up -d`; la contrapartida está
[al final del documento de despliegue](docs/despliegue.md#alternativa-sin-tarjeta-en-tu-propio-equipo).

## La web de cocina

- **Modo cocina**: un paso por pantalla, letra grande, temporizadores con aviso
  sonoro y **la pantalla no se apaga** mientras estás en él.
- Se avanza tocando, deslizando o con las flechas del teclado.
- Ingredientes y pasos se marcan con casillas que se recuerdan en el
  dispositivo.
- Selector de raciones: reescala las cantidades, y la lista de la compra sale ya
  escalada.
- Añádela a la pantalla de inicio de la tablet y se comporta como una app.

## API

Todas las rutas `/api/*` piden la clave en la cabecera `X-API-Key` (o `?key=…`,
más cómodo desde Atajos).

| Método | Ruta | Para qué |
|---|---|---|
| `POST` | `/api/recipes` | `{"url": "...", "wait": 240}` → devuelve la receta ya hecha |
| `GET` | `/api/recipes` | Lista de recetas (`?q=` busca por título o ingrediente) |
| `GET` | `/api/recipes/{id}` | Estado y receta completa |
| `GET` | `/api/recipes/{id}/shopping-list` | Lista de la compra (`?format=text`, `?servings=4`…) |
| `POST` | `/api/recipes/{id}/retry` | Reintentar una que falló |
| `DELETE` | `/api/recipes/{id}` | Borrarla |
| `GET` | `/healthz` | Estado del servicio y del modelo (sin clave) |

Con `wait` la petición no responde hasta que la receta está lista, mandando
mientras tanto espacios en blanco para que iOS no corte la conexión. Es lo que
permite que el Atajo sea una sola llamada, y lo que mantiene viva la instancia
de Cloud Run mientras trabaja.

```bash
curl -X POST https://TU-DIRECCION/api/recipes \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://www.instagram.com/reel/XXXX/", "wait": 240}'
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
├── schema_utils.py    adapta el esquema a lo que acepta cada modelo
├── shopping.py        construcción de la lista de la compra
├── storage.py         recetas como objetos (disco o Cloud Storage)
├── security.py        clave de API y sesión web
├── cli.py             procesar una URL desde la terminal
├── pipeline/
│   ├── download.py    yt-dlp: vídeo + pie del post
│   ├── media.py       ffmpeg: recompresión, fotogramas y audio
│   ├── transcribe.py  Whisper (solo para modelos que no oyen el vídeo)
│   ├── extract.py     material del vídeo → receta validada
│   ├── providers/     backends intercambiables (gemini, ollama, anthropic)
│   └── runner.py      orquestación y estados
├── templates/         web (Jinja2)
└── static/            estilos y modo cocina
docs/                  despliegue y Atajo de iOS
tests/                 pytest
```

No hay base de datos: cada receta es un JSON y su miniatura un JPEG, con un
índice para el listado. Así el mismo código funciona sobre disco y sobre Cloud
Storage, que es lo que permite desplegar donde no hay disco persistente.

## Desarrollo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
STORAGE_BACKEND=local uvicorn app.main:app --reload
```

## Notas y límites

- **Instagram exige sesión** para bastantes reels, y desde un centro de datos
  para casi todos: hay que configurar cookies
  ([cómo](docs/despliegue.md#3-cookies-de-instagram)). Es, con diferencia, la
  causa más habitual de que falle una receta, y hay que renovarlas cada pocas
  semanas.
- **Google Cloud pide una tarjeta** para activar la cuenta, aunque no cobre
  nada con este uso. Ponte una alerta de presupuesto de 1 € por tranquilidad.
- **Con la capa gratuita de Gemini**, Google puede usar lo que envías para
  entrenar sus modelos. Si prefieres que no salga nada de casa, usa `ollama`.
- **Uso personal.** Descarga vídeos de terceros para tu propio consumo; no
  publiques las recetas resultantes como si fueran tuyas ni las redistribuyas.
- **Repasa las cantidades** en repostería antes de fiarte: si el vídeo no las
  dice, el modelo las estima, y lo avisa en la ficha.
