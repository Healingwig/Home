# El Atajo de iOS: de Instagram a la receta y a Recordatorios

Este es el trozo que hace que todo sea cómodo: ves un reel, tocas **Compartir →
Guardar receta**, y al minuto tienes la receta en la tablet y los ingredientes
en tu lista de la compra.

No hace falta instalar ninguna app: se hace con **Atajos**, que ya viene con iOS.

---

## Antes de empezar

Necesitas dos datos del despliegue (ver [despliegue.md](despliegue.md)):

| Dato | Ejemplo |
|---|---|
| Dirección de tu app | `https://recetas-xxxxx-uc.a.run.app` |
| Tu `API_KEY` | `k7Fh2...` (la que generaste al desplegar) |

En lo que sigue los llamo `TU-DIRECCION` y `TU-CLAVE`.

---

## Atajo 1 — «Guardar receta» (el importante)

Son siete acciones. El servidor hace todo el trabajo en una sola petición: el
Atajo pregunta una vez y se queda esperando la respuesta.

### Configuración del atajo

1. Abre **Atajos** → **+** (arriba a la derecha).
2. Toca el nombre → **Renombrar** → `Guardar receta`.
3. En el mismo menú → **Detalles del atajo**:
   - Activa **Mostrar en la hoja de compartir**.
   - En **Tipos de entrada**, deja marcados **URLs** y **Texto** (Instagram
     comparte a veces texto con la URL dentro; el servidor sabe extraerla).

### Acciones, en orden

**1. Obtener URLs de la entrada**
- Como entrada, la variable mágica **Entrada del atajo**.

**2. Obtener contenido de la URL** *(hace la receta entera)*
- URL: `TU-DIRECCION/api/recipes`
- Despliega la flecha ▸:
  - **Método**: `POST`
  - **Encabezados**: clave `X-API-Key`, valor `TU-CLAVE`
  - **Cuerpo de la solicitud**: `JSON`
    - Campo **Texto** con clave `url` y valor la variable mágica **URLs**.
    - Campo **Número** con clave `wait` y valor `240`.

> `wait` es lo que hace que esta única acción no responda hasta que la receta
> está lista (hasta 4 minutos). Mientras tanto el servidor va mandando datos
> para que iOS no corte la conexión, así que no tienes que montar ningún bucle.

**3. Obtener valor de diccionario**
- Valor de `recipe.title` en **Contenido de la URL**. Renómbralo a `Titulo`
  (mantén pulsado → *Renombrar*).

**4. Obtener valor de diccionario**
- Valor de `id` en **Contenido de la URL**. Renómbralo a `IdReceta`.

**5. Obtener contenido de la URL** *(la lista de la compra)*
- URL: `TU-DIRECCION/api/recipes/` + variable `IdReceta` + `/shopping-list?format=text`
  (escribe el texto y arrastra la variable en medio)
- Método `GET`, encabezado `X-API-Key` = `TU-CLAVE`.

**6. Dividir texto**
- Entrada: el contenido anterior. Separador: **Líneas**.

**7. Repetir con cada elemento**
- Entrada: **Texto dividido**.
- Dentro: **Añadir nuevo recordatorio**
  - Recordatorio: variable **Elemento repetido**
  - Lista: tu **Lista de la compra**

**8. Mostrar notificación** *(opcional pero recomendable)*
- Texto: `Receta lista: ` + variable `Titulo`

### Probarlo

1. Abre Instagram, busca un reel de cocina.
2. **Compartir** (el avioncito) → **Atajos** → **Guardar receta**.
3. Al minuto llega la notificación y los ingredientes están en Recordatorios.

> **Si algo falla**, el campo `error` de la respuesta dice qué ha pasado. Lo más
> habitual es que hagan falta cookies de Instagram
> ([despliegue.md](despliegue.md#3-cookies-de-instagram)).

---

## Ajustes útiles de la lista de la compra

Parámetros que puedes añadir a la URL del paso 5:

| Parámetro | Por defecto | Para qué sirve |
|---|---|---|
| `servings=4` | las del vídeo | Reescala las cantidades a N raciones |
| `include_pantry=true` | `false` | Incluye sal, aceite, agua y azúcar (por defecto se omiten) |
| `include_optional=false` | `true` | Deja fuera los ingredientes opcionales |
| `prefix_title=true` | `false` | Añade el nombre del plato a cada línea: útil si mezclas varias recetas |
| `format=text` | `json` | Texto plano, una línea por producto (lo que quiere Atajos) |

Si sueles cocinar para cuatro, deja fija la URL con `&servings=4`: las
cantidades llegan ya escaladas.

---

## Atajo 2 (opcional) — «Añadir receta a la compra»

Para cocinar algo que guardaste hace semanas.

1. **Obtener contenido de la URL** → `TU-DIRECCION/api/recipes?limit=50`
   con el encabezado `X-API-Key`.
2. **Obtener valor de diccionario** → `recipes`.
3. **Elegir de la lista** (entrada: lo anterior). En los ajustes de la acción,
   pon `title` como **clave de título**.
4. **Obtener valor de diccionario** → `id` en el elemento elegido.
5. **Pedir entrada** → Número → `¿Para cuántas raciones?`
6. **Obtener contenido de la URL** →
   `TU-DIRECCION/api/recipes/[id]/shopping-list?format=text&servings=[Entrada]`
7. **Dividir texto** por líneas → **Repetir con cada elemento** →
   **Añadir nuevo recordatorio**.

---

## Si usas otra app para la compra

Cambia solo la acción **Añadir nuevo recordatorio** por la equivalente:

- **Bring!** → `Añadir artículo`
- **AnyList** → `Add Items to List`
- **Todoist / Things / Google Keep** → la acción de crear tarea de cada app
- **Notas** → `Añadir al ítem de nota`, apuntando a una nota fija

El resto no cambia: el servidor siempre da una línea de texto por producto.

---

## La tablet

Abre `TU-DIRECCION` en Safari, introduce tu `APP_PASSWORD` una vez y después
**Compartir → Añadir a pantalla de inicio**. Queda como una app: sin barra de
navegador y a pantalla completa.

Dentro de una receta, **👨‍🍳 Modo cocina** pasa a letra grande, un paso por
pantalla, con temporizadores y **evitando que la pantalla se apague** mientras
cocinas. Se avanza tocando, deslizando o con las flechas del teclado.
