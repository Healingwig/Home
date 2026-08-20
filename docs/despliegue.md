# Despliegue en Google Cloud Run (sin ordenador y gratis)

La app vive entera en la nube: se enciende cuando compartes un reel y se apaga
sola. No hace falta tener ningún ordenador encendido, ni router, ni VPN. Te da
una URL con HTTPS que funciona desde cualquier sitio.

**Qué se usa y por qué entra en la capa gratuita:**

| Servicio | Capa gratuita mensual | Lo que gastarás |
|---|---|---|
| Cloud Run | 180.000 s de CPU, 2 M peticiones | ~60 s de CPU por receta |
| Cloud Storage | 5 GB, 5.000 escrituras, 50.000 lecturas | unos KB por receta |
| Gemini (AI Studio) | Cuota diaria de peticiones | 1 petición por receta |

Con 30 recetas al mes usarías alrededor del 1 % de lo gratuito.

> **Hay que dar una tarjeta.** Google Cloud exige una forma de pago para
> activar la cuenta, aunque no cobre nada dentro de la capa gratuita. Si
> prefieres no darla, al final de este documento tienes la alternativa.

---

## 1. Preparativos (10 minutos, una vez)

### Clave de Gemini

En <https://aistudio.google.com/apikey> → **Create API key**. Es gratis y no
pide tarjeta. Guárdala.

### Proyecto de Google Cloud

1. Instala `gcloud`: <https://cloud.google.com/sdk/docs/install>
2. Entra y crea el proyecto:

```bash
gcloud auth login
gcloud projects create recetas-$USER --name="Recetas"
gcloud config set project recetas-$USER
```

3. Asocia una cuenta de facturación (en la consola web, *Facturación*) y activa
   los servicios:

```bash
gcloud services enable run.googleapis.com storage.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com
```

### Cubo para las recetas

```bash
# us-central1 es una de las regiones con almacenamiento en la capa gratuita.
gcloud storage buckets create gs://recetas-$USER --location=us-central1 \
    --uniform-bucket-level-access
```

---

## 2. Desplegar

```bash
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Guarda esta clave, la necesita el Atajo: $API_KEY"

gcloud run deploy recetas \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 2 \
  --set-env-vars "LLM_PROVIDER=gemini,STORAGE_BACKEND=gcs,GCS_BUCKET=recetas-$USER,DATA_DIR=/tmp/recetas" \
  --set-env-vars "GEMINI_API_KEY=TU-CLAVE-DE-GEMINI,API_KEY=$API_KEY,APP_PASSWORD=una-contraseña-corta"
```

Tarda unos minutos la primera vez (construye la imagen). Al terminar te imprime
la URL: `https://recetas-xxxxx-uc.a.run.app`. **Esa es `TU-DIRECCION`.**

Comprueba que está todo:

```bash
curl -s https://TU-DIRECCION/healthz
# {"ok":true,"ffmpeg":true,"provider":"gemini","provider_ready":true,...}
```

`--allow-unauthenticated` deja la URL accesible desde Internet, pero la app pide
tu `API_KEY` o tu contraseña en todas las rutas: sin ellas solo se ve la
pantalla de login.

> **Por qué `--timeout 300`:** en Cloud Run el contenedor se congela en cuanto
> responde, así que el trabajo se hace *durante* la petición del Atajo. Ese
> tiempo tiene que caber en el timeout.

---

## 3. Cookies de Instagram

Es lo que más se rompe. Desde un centro de datos, Instagram pide sesión
iniciada para casi todos los reels; sin cookies verás *«Instagram pide iniciar
sesión para este post»*.

1. En el navegador, inicia sesión en instagram.com **con una cuenta
   secundaria** — Instagram bloquea cuentas cuyas cookies se usan desde IPs
   raras, y no quieres que sea la tuya de verdad.
2. Instala una extensión que exporte cookies en formato Netscape («Get
   cookies.txt LOCALLY» o similar) y exporta las de `instagram.com`.
3. Súbelas como variable de entorno:

```bash
gcloud run services update recetas --region us-central1 \
  --set-env-vars "IG_COOKIES_B64=$(base64 -w0 cookies.txt)"   # macOS: base64 -i cookies.txt
```

Caducan cada pocas semanas. Cuando empiecen a fallar las descargas, repite el
paso 3 con cookies nuevas.

---

## 4. Actualizar y vigilar

```bash
gcloud run deploy recetas --source . --region us-central1   # redesplegar
gcloud run services logs tail recetas --region us-central1  # ver qué pasa
gcloud billing accounts list                                 # comprobar gasto
```

Para dormir tranquilo, ponte un **presupuesto con alerta de 1 €** en
*Facturación → Presupuestos y alertas*. Con este uso no debería saltar nunca.

### Copias de seguridad

Todo está en el cubo:

```bash
gcloud storage rsync -r gs://recetas-$USER/recetario ./copia-recetas
```

---

## 5. Cuánto tarda cada receta

| Paso | Tiempo |
|---|---|
| Arranque en frío del contenedor | 5–15 s (solo si llevaba rato parado) |
| Descarga del reel | 3–10 s |
| Recompresión del vídeo | 5–15 s |
| Gemini lee el vídeo y escribe la receta | 20–40 s |

En total, entre 30 s y 1,5 min. El Atajo mantiene una sola petición abierta
durante ese rato, así que no tienes que hacer nada.

---

## Si Google retira el modelo

Pasa cada pocos meses. El error de la app nombra el sustituto que recomienda
Google, y se cambia sin redesplegar:

```bash
gcloud run services update recetas --region us-central1 \
  --update-env-vars "GEMINI_MODEL=el-que-diga-el-error"
```

La lista completa está en <https://ai.google.dev/gemini-api/docs/models>.

---

## Cómo lee el vídeo

Con Gemini se le manda **el vídeo entero**, recomprimido para que quepa en una
petición: ve las imágenes (incluido el texto sobreimpreso con las cantidades) y
escucha el audio en la misma pasada. Por eso el despliegue en la nube no
necesita Whisper ni extraer fotogramas.

Si el vídeo no cabe ni recomprimido, la app cae sola al modo antiguo:
fotogramas sueltos con ffmpeg. Los modelos que no aceptan vídeo (`ollama`,
`anthropic`) usan siempre ese modo.

---

## Alternativa sin tarjeta: en tu propio equipo

Si prefieres no dar una tarjeta a Google, todo esto sigue funcionando en un
ordenador tuyo —— con la contrapartida de que **tiene que estar encendido**
cuando compartas un reel.

```bash
cp .env.example .env      # STORAGE_BACKEND=local, GEMINI_API_KEY, API_KEY
docker compose up -d --build
```

Entras desde el iPhone y la tablet con `http://IP-DE-TU-EQUIPO:8000` estando en
la misma Wi-Fi. Para que funcione también fuera de casa, **Tailscale** (plan
personal gratuito, sin tarjeta) da una URL con HTTPS visible solo desde tus
dispositivos:

```bash
tailscale serve --bg 8000
tailscale serve status
```

Una Raspberry Pi con `LLM_PROVIDER=gemini` sirve de sobra para dejarlo fijo.

### Modelo local, sin depender de nadie

Si además quieres que el vídeo no salga de casa, instala
[Ollama](https://ollama.com/download), descarga un modelo con visión y cambia
dos variables:

```bash
ollama pull qwen2.5vl:7b
```

```ini
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5vl:7b
```

Necesita 8–16 GB de RAM, tarda entre 1 y 5 minutos por receta y lee peor el
texto sobreimpreso. Para transcribir el audio (Ollama no lo hace):
`pip install -r requirements-whisper.txt`.

---

## Desarrollo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q

STORAGE_BACKEND=local uvicorn app.main:app --reload
python -m app.cli "https://www.instagram.com/reel/XXXXXX/"
```
