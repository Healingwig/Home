# Despliegue

La app es un contenedor Docker con un volumen para los datos. Necesita estar
accesible desde tu iPhone (para el Atajo) y desde la tablet, así que lo normal
es ponerla detrás de un dominio con HTTPS.

---

## 1. Configuración

```bash
cp .env.example .env
# genera una clave larga para el Atajo
python3 -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32))"
```

Edita `.env` y rellena como mínimo:

- `ANTHROPIC_API_KEY` — de https://console.anthropic.com/
- `API_KEY` — la que acabas de generar (la usará el Atajo)
- `APP_PASSWORD` — algo que puedas teclear en la tablet

## 2. Levantarlo

```bash
docker compose up -d --build
docker compose logs -f
```

Comprueba que responde:

```bash
curl http://localhost:8000/healthz
# {"ok":true,"ffmpeg":true}
```

## 3. Ponerlo en Internet

Necesitas HTTPS: Atajos no manda cabeceras a `http://` fuera de tu red, y no
quieres tu `API_KEY` viajando en claro.

**Opción A — Cloudflare Tunnel** (sin abrir puertos en el router):

```bash
cloudflared tunnel --url http://localhost:8000
```

Para algo permanente, crea un túnel con nombre y apúntalo a un subdominio tuyo.

**Opción B — Caddy delante** (si ya tienes un servidor con dominio):

```
recetas.tudominio.com {
    reverse_proxy localhost:8000
}
```

Caddy pide el certificado de Let's Encrypt solo.

**Opción C — Tailscale**: instala Tailscale en el servidor, el iPhone y la
tablet, y usa `https://<nombre-maquina>.<tu-tailnet>.ts.net` con
`tailscale serve`. Es la opción más privada: nada queda expuesto a Internet.

---

## 4. Cookies de Instagram

Muchos reels (y prácticamente todos si el servidor está en un centro de datos)
piden sesión iniciada. Sin cookies verás el error *«Instagram pide iniciar
sesión para este post»*.

1. En un navegador de escritorio, inicia sesión en instagram.com **con una
   cuenta secundaria** — Instagram puede bloquear cuentas cuyas cookies se usan
   desde IPs raras.
2. Instala una extensión que exporte cookies en formato Netscape
   («Get cookies.txt LOCALLY» o similar) y exporta las de `instagram.com`.
3. Copia el fichero al volumen de datos y apunta ahí la variable:

```bash
cp cookies_instagram.txt ./data/
# en .env
IG_COOKIES_FILE=/data/cookies_instagram.txt
```

4. `docker compose restart`.

Las cookies caducan cada pocas semanas o meses; cuando empiecen a fallar las
descargas, repite la exportación.

---

## 5. Transcripción del audio

Por defecto se usa `faster-whisper` con el modelo `small` en CPU. Al primer
vídeo se descarga el modelo (~500 MB) dentro del volumen `/data/modelos`, así
que ese primer procesado tarda más.

- Servidor con poca RAM (menos de 2 GB): pon `WHISPER_MODEL=base` o
  `TRANSCRIBER=none`.
- Servidor holgado: `WHISPER_MODEL=medium` mejora bastante con recetas
  habladas rápido.

Sin transcripción la app sigue funcionando: se apoya en el pie del post y en
los fotogramas, que es de donde sale la mayor parte de la información.

---

## 6. Coste aproximado

Por receta se envían unos 14 fotogramas más el texto: en torno a 20.000 tokens
de entrada y 2.000 de salida con Claude Opus 5, es decir **unos 0,15 € por
receta**. Si procesas muchas y quieres bajarlo:

- `FRAME_COUNT=8` y `FRAME_MAX_DIM=768` (aproximadamente la mitad de coste).
- `CLAUDE_EFFORT=medium`.
- `CLAUDE_MODEL=claude-sonnet-5` si prefieres un modelo más barato; la calidad
  de lectura del texto sobreimpreso en los vídeos baja un poco.

---

## 7. Copias de seguridad

Todo vive en el volumen `./data`:

```
data/
├── recetas.sqlite3     # recetas e ingredientes
├── media/              # miniaturas
└── modelos/            # modelo de Whisper (regenerable)
```

Basta con copiar `recetas.sqlite3` y `media/`.

---

## Ejecutar sin Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # necesita ffmpeg en el PATH
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Procesar una URL suelta desde la terminal, sin servidor:

```bash
python -m app.cli "https://www.instagram.com/reel/XXXXXX/"
python -m app.cli "https://www.instagram.com/reel/XXXXXX/" --json --raciones 4
```
