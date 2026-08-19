# 🍳 Recetas desde Instagram

Compartes un reel de cocina desde el iPhone y, un par de minutos después:

- la **receta paso a paso** está en una web pensada para leer en la tablet
  mientras cocinas, y
- los **ingredientes con sus cantidades** están en tu lista de la compra de
  Recordatorios.

No hay que instalar ninguna app en el iPhone: se usa **Atajos**, que ya viene
con iOS, más un pequeño servidor que corre **en tu propio ordenador**. No se
publica nada en Internet y **se puede usar sin pagar nada**.

```
Instagram → Compartir → Atajo «Guardar receta»
                            │
                            ▼
            tu ordenador (esta aplicación)
       yt-dlp → ffmpeg → Whisper → modelo (a tu elección)
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

Con eso, el modelo devuelve una receta estructurada (ingredientes con cantidad,
unidad y sección del supermercado; pasos autocontenidos con tiempos y
temporizadores) validada contra un esquema fijo. Lo que ha tenido que deducir
queda anotado en la ficha, así que sabes de qué fiarte.

## Qué modelo usa

Es intercambiable con una variable del `.env`. Las tres opciones dan el mismo
resultado estructurado; cambian el coste y la calidad de lectura.

| `LLM_PROVIDER` | Coste | Necesita | Bueno para |
|---|---|---|---|
| `gemini` *(por defecto)* | **Gratis** (capa gratuita de AI Studio) | Una clave, sin tarjeta | Lo normal: funciona en cualquier equipo |
| `ollama` | **Gratis** | 8–16 GB de RAM en tu equipo | Que no salga nada de tu casa |
| `anthropic` | ~0,15 €/receta | Saldo de la API de Claude | La mejor lectura del texto sobreimpreso |

La comparación completa está en
[docs/despliegue.md](docs/despliegue.md#1-elegir-quién-lee-los-vídeos).
Todo lo demás (descarga, fotogramas, transcripción con Whisper, la web) es
software libre que corre en local y no cuesta nada.

## Puesta en marcha

```bash
cp .env.example .env      # GEMINI_API_KEY (gratis), API_KEY y APP_PASSWORD
docker compose up -d --build
curl http://localhost:8000/healthz
```

Después, desde el iPhone y la tablet de tu red, la app está en
`http://IP-DE-TU-ORDENADOR:8000`. Los dos documentos que quedan:

1. **[docs/despliegue.md](docs/despliegue.md)** — elegir modelo, entrar desde
   tus dispositivos (en casa y fuera, con Tailscale), cookies de Instagram y
   copias de seguridad.
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
curl -X POST http://192.168.1.42:8000/api/recipes \
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
├── schema_utils.py    adapta el esquema JSON a cada modelo
├── cli.py             procesar una URL desde la terminal
├── pipeline/
│   ├── download.py    yt-dlp: vídeo + pie del post
│   ├── media.py       ffmpeg: fotogramas y audio
│   ├── transcribe.py  Whisper (opcional)
│   ├── extract.py     material del vídeo → receta validada
│   ├── providers/     backends intercambiables (ollama, gemini, anthropic)
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
- **El ordenador tiene que estar encendido** para que el Atajo funcione. Una
  Raspberry Pi con `LLM_PROVIDER=gemini` da de sobra si quieres dejarlo fijo.
- **Con la capa gratuita de Gemini**, Google puede usar lo que envías para
  entrenar sus modelos. Si prefieres que no salga nada de casa, usa `ollama`.
- **Repasa las cantidades** en recetas de repostería antes de fiarte: si el
  vídeo no las dice, el modelo las estima, y lo avisa en la ficha con la
  confianza y las advertencias.
