# Puesta en marcha (sin pagar nada)

Todo esto corre en tu propio ordenador y no se publica en ningún sitio: solo tú
lo ves, desde tu red o desde tu VPN privada.

**Lo que cuesta dinero: nada.** Docker, yt-dlp, ffmpeg, Whisper, Tailscale (plan
personal) y las capas gratuitas de los modelos cubren el uso de una persona.

---

## 1. Elegir quién lee los vídeos

Es la única pieza donde hay que decidir algo. Las tres opciones funcionan con el
mismo código; se cambia con una variable.

| | `gemini` *(por defecto)* | `ollama` | `anthropic` |
|---|---|---|---|
| **Coste** | Gratis (capa gratuita) | Gratis | ~0,15 €/receta |
| **Hardware** | Cualquiera, hasta una Raspberry Pi | 8–16 GB de RAM; ideal con GPU | Cualquiera |
| **Sale de tu casa** | Sí, a Google | No, nada | Sí, a Anthropic |
| **Lee el texto del vídeo** | Muy bien | Aceptable | Excelente |
| **Tiempo por receta** | 20–40 s | 1–5 min (sin GPU, más) | 30–60 s |
| **Límites** | Cuota diaria generosa para uso personal | Ninguno | Los de tu saldo |

**Recomendación:** empieza con `gemini`. Es gratis, no necesita hardware y la
calidad es más que suficiente. Si prefieres que no salga nada de casa, pásate a
`ollama` cambiando una línea del `.env`.

### Opción A — Gemini (gratis, recomendada)

1. Entra en <https://aistudio.google.com/apikey> con tu cuenta de Google.
2. **Create API key**. No pide tarjeta.
3. En el `.env`:

```ini
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...
```

> Ojo: en la capa gratuita, Google puede usar lo que envías para mejorar sus
> modelos. Para reels de cocina da igual, pero conviene saberlo. Si te molesta,
> usa `ollama`.

### Opción B — Ollama (gratis y sin terceros)

**En Mac**, instala la app desde <https://ollama.com/download>. No la metas en
Docker: dentro del contenedor no usa la GPU de Apple y va muchísimo más lento.

```bash
ollama pull qwen2.5vl:7b     # ~6 GB, entiende imágenes
```

**En Linux con Docker:**

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen2.5vl:7b
```

En el `.env`:

```ini
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal:11434   # Ollama en el sistema
# OLLAMA_HOST=http://ollama:11434               # Ollama en el perfil de Docker
OLLAMA_MODEL=qwen2.5vl:7b
```

Si tu equipo va justo, usa un modelo de solo texto y renuncia a los fotogramas
(la mayor parte de la receta sale del pie del post y del audio):

```ini
OLLAMA_MODEL=llama3.1:8b
FRAME_COUNT=0
```

### Opción C — Claude (de pago)

```bash
pip install -r requirements-anthropic.txt   # o descomenta la línea del Dockerfile
```

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 2. Arrancar

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # para API_KEY
# edita .env: LLM_PROVIDER, la clave del modelo, API_KEY y APP_PASSWORD

docker compose up -d --build
```

Comprueba que está todo en su sitio:

```bash
curl -s http://localhost:8000/healthz
# {"ok":true,"ffmpeg":true,"provider":"gemini","provider_ready":true,...}
```

Si `provider_ready` es `false`, el campo `provider_detail` dice exactamente qué
falta (una clave, un modelo sin descargar, Ollama apagado…).

---

## 3. Entrar desde el iPhone y la tablet

### En casa (lo normal, y gratis del todo)

Averigua la IP local del ordenador:

```bash
ipconfig getifaddr en0        # macOS
hostname -I | awk '{print $1}' # Linux
```

Esa es tu dirección: `http://192.168.1.42:8000`. Funciona tal cual en el
navegador de la tablet y en el Atajo del iPhone mientras estéis en la misma
Wi-Fi. Atajos permite `http://` sin problemas.

Conviene fijar la IP del ordenador en el router (reserva DHCP) para que no
cambie y no tengas que retocar el Atajo.

### Fuera de casa (opcional, también gratis)

**Tailscale**, plan personal: gratis hasta 100 dispositivos.

1. Crea la cuenta en <https://tailscale.com> e instala Tailscale en el
   ordenador, el iPhone y la tablet.
2. En el ordenador:

```bash
tailscale serve --bg 8000
tailscale serve status     # te dice la URL https://tu-equipo.tu-tailnet.ts.net
```

Esa URL tiene HTTPS de verdad y **solo es visible desde tus dispositivos**: no
hay nada expuesto a Internet ni puertos abiertos en el router. Úsala en el
Atajo y funcionará dentro y fuera de casa.

> El ordenador tiene que estar encendido para que el Atajo funcione. Si quieres
> que esté siempre disponible, una Raspberry Pi 4/5 con `LLM_PROVIDER=gemini`
> sirve de sobra (con `ollama` no: le falta músculo).

---

## 4. Cookies de Instagram

Muchos reels piden sesión iniciada. Sin cookies verás el error *«Instagram pide
iniciar sesión para este post»*.

Corriendo desde tu casa fallará bastante menos que desde un servidor alquilado,
pero acabará pasando:

1. En un navegador de escritorio, inicia sesión en instagram.com **con una
   cuenta secundaria**.
2. Instala una extensión que exporte cookies en formato Netscape
   («Get cookies.txt LOCALLY» o similar) y exporta las de `instagram.com`.
3. Copia el fichero a `./data/` y en el `.env`:

```ini
IG_COOKIES_FILE=/data/cookies_instagram.txt
```

4. `docker compose restart`.

Las cookies caducan cada pocas semanas; cuando empiecen a fallar las descargas,
repite la exportación.

---

## 5. Transcripción del audio

Whisper corre en local y es gratis. Al primer vídeo se descarga el modelo
(~500 MB) dentro de `./data/modelos`, así que ese primer procesado tarda más.

- Equipo justo de RAM: `WHISPER_MODEL=base`, o `TRANSCRIBER=none`.
- Equipo holgado: `WHISPER_MODEL=medium` va mejor con recetas habladas rápido.

Sin transcripción la app sigue funcionando con el pie del post y los fotogramas.

---

## 6. Copias de seguridad

Todo vive en `./data`:

```
data/
├── recetas.sqlite3     # tus recetas
├── media/              # miniaturas
└── modelos/            # Whisper (se vuelve a descargar solo)
```

Con copiar `recetas.sqlite3` y `media/` de vez en cuando basta.

---

## Sin Docker

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
