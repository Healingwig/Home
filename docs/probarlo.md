# Cómo probarlo (desde la tablet, sin ordenador)

Desplegar necesita una terminal, pero no un ordenador: **Google Cloud Shell** es
una terminal dentro del navegador y funciona desde la tablet. Es gratis y viene
con todo instalado.

El plan es probar por partes, de menos a más riesgo, para que cuando algo falle
sepas exactamente qué ha fallado:

| | Qué pruebas | Cuánto tarda |
|---|---|---|
| 1 | Que la app despliega y arranca | ~20 min la primera vez |
| 2 | La web y el modo cocina, con una receta de ejemplo | 1 min |
| 3 | Una receta de verdad, desde el navegador | 2 min |
| 4 | El Atajo, compartiendo desde Instagram | 10 min |

---

## Paso 1 — Desplegar desde Cloud Shell

Antes de empezar, saca tu clave de Gemini en
<https://aistudio.google.com/apikey> (**Create API key**, es gratis y no pide
tarjeta) y tenla a mano.

### 1.1 Abrir la terminal

Abre <https://shell.cloud.google.com> en la tablet y entra con tu cuenta de
Google.

**Lo que verás es un editor de código**, con una pantalla de bienvenida que
pone *«Code OSS for Cloud Shell»*. La terminal no sale sola: ábrela en el menú
de arriba con **Terminal → New Terminal**. Aparece abajo, con un símbolo del
sistema tipo `tunombre@cloudshell:~$`.

- La primera vez sale un aviso de **Authorize** o de aceptar las condiciones:
  acéptalo, es lo que le da permiso a la terminal para usar tu cuenta.
- Si nunca has usado Google Cloud, te mandará antes a
  <https://console.cloud.google.com> a aceptar los términos y elegir país.
- Consejo para la tablet: un teclado Bluetooth ayuda bastante. Para pegar
  texto, mantén pulsado dentro de la terminal.

### 1.2 Crear el proyecto

En la terminal:

```bash
gcloud projects create recetas-$RANDOM --name="Recetas"
gcloud projects list
```

El segundo comando lista tus proyectos: copia el `PROJECT_ID` que empieza por
`recetas-` y actívalo:

```bash
gcloud config set project EL-ID-QUE-HAS-COPIADO
```

### 1.3 Activar la facturación

Esto hay que hacerlo en la web, no en la terminal:
<https://console.cloud.google.com/billing> → **Vincular una cuenta de
facturación** al proyecto que acabas de crear. Pide tarjeta, pero con este uso
no llega a cobrar nada (ver [despliegue.md](despliegue.md)).

### 1.4 Traer el código

```bash
git clone -b claude/instagram-recipe-app-ypfz15 https://github.com/Healingwig/Home.git recetas
```

<details>
<summary>Si el repositorio es privado, hay que identificarse antes</summary>

Mira si Cloud Shell trae la herramienta de GitHub:

```bash
command -v gh
```

**Si contesta con una ruta** (lo más cómodo):

```bash
gh auth login
```

Elige *GitHub.com* → *HTTPS* → *Login with a web browser*. Te da un código de 8
caracteres; ábrelo en <https://github.com/login/device> en otra pestaña de la
misma tablet, pégalo y autoriza. Luego:

```bash
gh repo clone Healingwig/Home recetas -- -b claude/instagram-recipe-app-ypfz15
```

**Si no contesta nada**, usa un token de acceso:

1. Ve a <https://github.com/settings/personal-access-tokens/new>
2. **Repository access** → *Only select repositories* → `Healingwig/Home`
3. **Permissions** → *Repository permissions* → **Contents: Read-only**
4. **Generate token** y copia el `github_pat_...`

```bash
git clone -b claude/instagram-recipe-app-ypfz15 \
  https://TU-TOKEN@github.com/Healingwig/Home.git recetas
```

</details>

### 1.5 Desplegar

```bash
cd recetas
bash scripts/desplegar.sh
```

El script te pide la clave de Gemini y una contraseña para la web, y al
terminar imprime dos cosas:

```
Dirección de la app : https://recetas-xxxxx-uc.a.run.app
Clave para el Atajo : k7Fh2...
```

**Apunta las dos.** La clave del Atajo no se vuelve a mostrar (si la pierdes,
el propio script te dice cómo recuperarla).

### 1.6 Comprobar que respira

```bash
curl -s https://TU-DIRECCION/healthz
```

Tiene que decir `"ok":true` y `"provider_ready":true`. Si `provider_ready` es
`false`, el campo de al lado explica qué falta.

---

## Paso 2 — La web y el modo cocina (sin gastar ningún reel)

Abre `https://TU-DIRECCION` en la tablet e introduce la contraseña que pusiste.

Verás el recetario vacío y un botón **«Ver una receta de ejemplo»**. Tócalo:
guarda una tortilla de patatas escrita a mano, sin pasar por Instagram ni por
Gemini. Sirve para ver cómo queda todo:

- Toca **👨‍🍳 Modo cocina**: un paso por pantalla, letra grande. Avanza
  deslizando el dedo. Comprueba que **la pantalla no se apaga sola**.
- En el paso 2 hay un temporizador de 20 minutos: arráncalo y déjalo unos
  segundos para ver que va (suena y vibra al acabar; puedes pararlo tocándolo).
- Cambia el selector de **raciones** a 8 y mira cómo se recalculan las
  cantidades.
- Marca ingredientes y pasos: las casillas se recuerdan al recargar.

Si esto se ve bien en tu tablet, la parte de cocinar ya está resuelta. Cuando
te canses, bórrala con el botón del final de la ficha.

> Ahora es buen momento para **Compartir → Añadir a pantalla de inicio**: queda
> como una app, sin barra de navegador.

---

## Paso 3 — Una receta de verdad, desde el navegador

Antes de pelearte con el Atajo, prueba el motor desde la web, que enseña los
errores con todas sus letras.

1. Busca en Instagram un reel de cocina y copia su enlace
   (**Compartir → Copiar enlace**).
2. En la web de tu app, pégalo en el cuadro de arriba y dale a
   **Convertir en receta**.
3. Te lleva a una pantalla de «Preparando la receta…» que se refresca sola.
   Entre 30 s y 1,5 min debería aparecer la receta.

**Si sale un error**, casi siempre es uno de estos dos:

- *«Instagram pide iniciar sesión para este post»* → hacen falta cookies. Sigue
  la sección de abajo.
- *«Falta GEMINI_API_KEY»* o *«La GEMINI_API_KEY no es válida»* → la clave está
  mal. Corrígela desde Cloud Shell:

```bash
gcloud run services update recetas --region us-central1 \
  --set-env-vars "GEMINI_API_KEY=la-clave-buena"
```

Para ver qué pasó por dentro:

```bash
gcloud run services logs tail recetas --region us-central1
```

Cuando salga bien, **repasa la receta contra el vídeo**: mira si las cantidades
cuadran y lee el desplegable de avisos, que dice qué ha tenido que deducir.

---

## Paso 4 — El Atajo

Con los pasos anteriores en verde, monta el Atajo siguiendo
[atajo-ios.md](atajo-ios.md). Son siete acciones y necesitas la dirección y la
clave del paso 1.

Pruébalo con un reel y comprueba las tres cosas: llega la notificación, la
receta aparece en la web y los ingredientes están en Recordatorios.

---

## Las cookies de Instagram (el punto pegajoso)

Instagram exige sesión iniciada para muchos reels, y desde un servidor de
Google para casi todos. Necesita un fichero de cookies en formato Netscape, y
**exportarlo es la única parte incómoda sin ordenador**:

- **Con un ordenador prestado** (5 minutos y ya está): inicia sesión en
  instagram.com **con una cuenta secundaria**, instala la extensión «Get
  cookies.txt LOCALLY», exporta las cookies de instagram.com y pásate el
  fichero al iPad.
- **Solo con el iPad**: Safari en iPadOS admite extensiones, y algunas
  (Cookie-Editor, por ejemplo) exportan cookies en ese formato. Debería
  funcionar, pero no lo he podido comprobar.

Con el fichero en la tablet, súbelo a Cloud Shell (menú **⋮ → Subir**) y:

```bash
gcloud run services update recetas --region us-central1 \
  --set-env-vars "IG_COOKIES_B64=$(base64 -w0 cookies.txt)"
```

Usa una cuenta secundaria: Instagram bloquea cuentas cuyas cookies se usan
desde direcciones raras. Caducan cada pocas semanas; cuando vuelvan a fallar
las descargas, repite el comando con cookies nuevas.

---

## Probar sin desplegar nada

Para depurar una URL concreta y ver el resultado en la propia terminal, sin
pasar por la web:

```bash
# en Cloud Shell, dentro de la carpeta del proyecto
sudo apt-get install -y ffmpeg
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export LLM_PROVIDER=gemini GEMINI_API_KEY=tu-clave
export STORAGE_BACKEND=local DATA_DIR=./data

python -m app.cli "https://www.instagram.com/reel/XXXXXX/"
```

Imprime la receta y la lista de la compra en la terminal. Añade `--json` para
ver el resultado en crudo, o `--raciones 6` para reescalarla.

Y para comprobar que no has roto nada si tocas el código:

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## Cómo desmontarlo

Si decides que no lo quieres, se borra entero y deja de existir cualquier
gasto:

```bash
gcloud run services delete recetas --region us-central1
gcloud storage rm -r gs://TU-CUBO
```
