# El Atajo de iOS: de Instagram a la receta y a Recordatorios

Este es el trozo que hace que todo sea cómodo: ves un reel, tocas **Compartir →
Guardar receta**, y a los dos minutos tienes la receta en la tablet y los
ingredientes en tu lista de la compra.

No hace falta instalar ninguna app: se hace con **Atajos** (viene con iOS).

---

## Antes de empezar

Necesitas dos datos del servidor que has desplegado (ver [despliegue.md](despliegue.md)):

| Dato | Ejemplo |
|---|---|
| Dirección de tu API | `https://recetas.tudominio.com` |
| Tu `API_KEY` | `k7Fh2...` (la que pusiste en el `.env`) |

En lo que sigue los llamo `TU-DOMINIO` y `TU-CLAVE`.

---

## Atajo 1 — «Guardar receta» (el importante)

### Configuración del atajo

1. Abre **Atajos** → **+** (arriba a la derecha).
2. Toca el nombre del atajo → **Renombrar** → `Guardar receta`.
3. En el mismo menú → **Detalles del atajo**:
   - Activa **Mostrar en la hoja de compartir**.
   - En **Tipos de entrada de la hoja de compartir**, deja marcados solo
     **URLs** y **Texto** (Instagram comparte a veces texto con la URL dentro;
     la API sabe extraerla).

### Acciones, en orden

**1. Obtener URLs de la entrada**
- Busca la acción `Obtener URLs de la entrada`.
- Como entrada, elige la variable mágica **Entrada del atajo**.

**2. Obtener contenido de la URL** *(crear la receta)*
- URL: `https://TU-DOMINIO/api/recipes`
- Despliega la flecha ▸ para ver las opciones:
  - **Método**: `POST`
  - **Encabezados**: añade uno → clave `X-API-Key`, valor `TU-CLAVE`
  - **Cuerpo de la solicitud**: `JSON`
    - Añade un campo de tipo **Texto** con clave `url` y valor la variable
      mágica **URLs** (la salida del paso 1).

**3. Obtener valor de diccionario**
- Obtener el valor de `id` en **Contenido de la URL**.
- Renombra la variable (mantén pulsado → *Renombrar*) a `IdReceta`.

**4. Repetir 40 veces** *(esperar a que la receta esté lista)*

Dentro del bucle:

  **4.1. Obtener contenido de la URL**
  - URL: `https://TU-DOMINIO/api/recipes/` + variable `IdReceta`
    (escribe la primera parte y arrastra la variable justo al final)
  - Método `GET`, encabezado `X-API-Key` = `TU-CLAVE`.

  **4.2. Obtener valor de diccionario** → valor de `status` en **Contenido de la URL**.

  **4.3. Si** `Valor del diccionario` **es** `ready`:

  Dentro del *Si* (todo lo que sigue va aquí dentro):

  - **Obtener contenido de la URL**
    `https://TU-DOMINIO/api/recipes/[IdReceta]/shopping-list?format=text`
    · Método `GET` · encabezado `X-API-Key` = `TU-CLAVE`
  - **Dividir texto** → por **Líneas** (entrada: el contenido anterior)
  - **Repetir con cada elemento** (entrada: **Texto dividido**)
    - **Añadir nuevo recordatorio**
      - Recordatorio: variable **Elemento repetido**
      - Lista: tu **Lista de la compra**
  - **Obtener valor de diccionario** → `title` en la respuesta del paso 4.1
    (usa **Contenido de la URL** de ese paso; si te lía, usa `recipe` → `title`)
  - **Mostrar notificación**: `Receta lista: [title]`
  - **Detener este atajo**

  **4.4. Si no:**
  - **Esperar** `5` segundos

  Fin del *Si*. Fin del *Repetir*.

**5. Mostrar notificación** (fuera del bucle)
- `La receta está tardando más de lo normal. Ábrela en TU-DOMINIO dentro de un rato.`

### Probarlo

1. Abre Instagram, busca un reel de cocina.
2. **Compartir** (el avioncito) → **Atajos** → **Guardar receta**.
3. A los 30–90 s recibes la notificación y los ingredientes aparecen en
   Recordatorios.

> **Truco:** en el paso 4.3, cambia la URL de la lista de la compra por
> `…/shopping-list?format=text&servings=4` si sueles cocinar para cuatro. La API
> reescala las cantidades sola.

---

## Ajustes útiles de la lista de la compra

Todos son parámetros que puedes añadir a la URL del paso 4.3:

| Parámetro | Por defecto | Para qué sirve |
|---|---|---|
| `servings=4` | las del vídeo | Reescala las cantidades a N raciones |
| `include_pantry=true` | `false` | Incluye sal, aceite, agua y azúcar (por defecto se omiten) |
| `include_optional=false` | `true` | Deja fuera los ingredientes marcados como opcionales |
| `prefix_title=true` | `false` | Añade el nombre del plato a cada línea: útil si mezclas varias recetas en la misma lista |
| `format=text` | `json` | Texto plano, una línea por producto (lo que quiere Atajos) |

---

## Atajo 2 (opcional) — «Añadir receta a la compra»

Para cuando quieres cocinar algo que guardaste hace semanas.

1. **Obtener contenido de la URL** → `https://TU-DOMINIO/api/recipes?limit=50`
   con el encabezado `X-API-Key`.
2. **Obtener valor de diccionario** → `recipes`.
3. **Elegir de la lista** (entrada: lo anterior). En los ajustes de la acción,
   pon `title` como **clave de título**.
4. **Obtener valor de diccionario** → `id` en el elemento elegido.
5. **Pedir entrada** → Número → `¿Para cuántas raciones?`
6. **Obtener contenido de la URL** →
   `https://TU-DOMINIO/api/recipes/[id]/shopping-list?format=text&servings=[Entrada]`
7. **Dividir texto** por líneas → **Repetir con cada elemento** → **Añadir nuevo recordatorio**.

---

## Si usas otra app para la compra

Solo cambia la acción **Añadir nuevo recordatorio** por la equivalente:

- **Bring!** → acción `Añadir artículo` (la app publica su propia acción de Atajos).
- **AnyList** → acción `Add Items to List`.
- **Google Keep / Todoist / Things** → acción de crear tarea de cada app.
- **Notas** → `Añadir al ítem de nota`, apuntando a una nota fija.

El resto del atajo no cambia: la API siempre te da una línea de texto por producto.

---

## La tablet

En la tablet, abre `https://TU-DOMINIO`, introduce tu `APP_PASSWORD` una vez y
después **Compartir → Añadir a pantalla de inicio**. Queda como una app: sin
barra de navegador y a pantalla completa.

Dentro de una receta, el botón **👨‍🍳 Modo cocina** pasa a letra grande, un paso
por pantalla, con temporizadores y **evitando que la pantalla se apague**
mientras cocinas. Se avanza tocando, deslizando o con las flechas del teclado.
