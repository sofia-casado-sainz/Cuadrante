# Cuadrante (versión independiente)

Mi app personal de tareas y avisos de la UFV. Reúne automáticamente las entregas y anuncios de las asignaturas de Canvas que tengo marcadas como favoritas (con la ⭐ del dashboard), junto con mi horario de clases, en un único sitio que instalo en el móvil como una app normal. Es gratuita, no depende de ninguna suscripción de Claude, y se actualiza sola cada 4 horas — y también sola en el propio móvil en cuanto publico un cambio nuevo.

## Qué monté (todo gratis)

1. Un proyecto de **Firebase** → guarda mis tareas/avisos y controla quién entra.
2. Un repositorio de **GitHub** → aloja la web y ejecuta la sincronización sola.
3. La web publicada con **GitHub Pages** → el enlace que abro en el móvil.

## Paso 1 — Crear el proyecto Firebase

1. Voy a [console.firebase.google.com](https://console.firebase.google.com) → **Crear un proyecto** (le pongo el nombre que quiera, ej. "cuadrante").
2. En el menú de la izquierda, entro en **Firestore Database** → **Crear base de datos** → modo producción → la ubicación da igual (elijo `eur3` para que esté en Europa).
3. Cuando está creada, voy a la pestaña **Reglas** y pego el contenido del archivo `firestore.rules` de esta carpeta, sustituyendo lo que haya. Pulso **Publicar**.
4. En el menú de la izquierda, entro en **Authentication** → **Comenzar** → pestaña **Sign-in method** → activo **Correo electrónico/contraseña** (no uso Google).
5. En la pestaña **Users** de Authentication, pulso **Add user** y creo mi propio usuario: mi email de la UFV (`9206029@alumnos.ufv.es`) y una contraseña que elijo yo. Con esa contraseña entro luego en la app — no hay registro público, la creo yo a mano una sola vez.
6. Voy al icono de engranaje (arriba a la izquierda) → **Configuración del proyecto** → bajo hasta "Tus apps" → pulso el icono `</>` (web) → le doy un nombre → **Registrar app**. Me muestra un bloque `firebaseConfig = {...}` — copio esos valores.
7. Abro `index.html` de esta carpeta, busco `const firebaseConfig = {` y sustituyo los valores `"TU_..."` por los que acabo de copiar. Guardo.

## Paso 2 — Clave para que el robot pueda escribir

1. En Firebase, **Configuración del proyecto** → pestaña **Cuentas de servicio** → **Generar nueva clave privada**. Se descarga un archivo `.json` — lo guardo, lo necesito en el Paso 4 (nunca lo subo a GitHub directamente).

## Paso 3 — Crear el repositorio en GitHub

1. En [github.com](https://github.com), creo un repositorio nuevo, **público** (ej. "cuadrante"). Tiene que ser público porque GitHub Pages (Paso 5) no funciona con repositorios privados en la cuenta gratuita — no pasa nada por ello: mi token de Canvas y las credenciales de Firebase nunca van en el código, viajan aparte como "secretos" cifrados (Paso 4) que nadie puede leer ni descargar, y mis tareas/avisos reales viven en Firestore protegidos por `firestore.rules`, que solo me deja pasar a mí. Lo único visible para cualquiera sería el código en sí, no mis datos.
2. Subo TODOS los archivos de esta carpeta (`index.html`, `sync_canvas.py`, `sw.js`, `firestore.rules`, la carpeta `.github/`) — los arrastro en la web de GitHub con "Add file → Upload files", o con `git` si lo conozco.

## Paso 4 — Añadir mis secretos al repositorio

En el repositorio → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, creo estos:

| Nombre exacto | Valor |
|---|---|
| `CANVAS_DOMAIN` | `ufv-es.instructure.com` |
| `CANVAS_TOKEN` | mi token de acceso personal de Canvas |
| `FIREBASE_CREDENTIALS` | abro el `.json` del Paso 2 con un editor de texto y pego **todo su contenido** tal cual |
| `VAPID_PRIVATE_KEY` | opcional, solo si quiero avisos push — ver Paso 6 |

## Paso 5 — Publicar la web con GitHub Pages

1. En el repositorio → **Settings** → **Pages**.
2. En "Source" elijo **Deploy from a branch**, rama `main`, carpeta `/ (root)` → **Save**.
3. Espero un minuto y GitHub me da un enlace tipo `https://tu-usuario.github.io/cuadrante/` — esa es mi app.

## Paso 6 — Avisos push en el móvil (opcional)

Si quiero recibir una notificación en el iPhone cuando salga una tarea nueva o el día que toca entregar algo:

1. Genero un par de claves VAPID (por ejemplo con `pip install py_vapid && vapid --gen`, o pidiéndoselo a Claude una vez).
2. La clave pública ya va escrita en `index.html` (constante `VAPID_PUBLIC_KEY`) — si genero unas nuevas, la sustituyo ahí.
3. La clave privada la guardo como secreto `VAPID_PRIVATE_KEY` en GitHub (Paso 4).
4. En la app, dentro de la pestaña Tareas, toco **🔔 Activar avisos** (solo funciona con la app añadida a la pantalla de inicio, no desde el navegador).

Si no me interesa esto, lo dejo sin configurar y el botón simplemente no hace nada — el resto de la app funciona igual.

## Paso 7 — Probar la sincronización

1. En el repositorio → pestaña **Actions** → veo el workflow "Sincronizar Canvas" → pulso **Run workflow** para probarlo ya mismo en vez de esperar 4 horas.
2. Si falla, el propio log de GitHub Actions me dice la línea exacta del error (normalmente un secreto mal copiado, o un fallo de sangría si edité `sync_canvas.py` a mano).

## Paso 8 — Instalarla en el móvil

Abro el enlace de GitHub Pages en el teléfono, inicio sesión con mi email y contraseña de la UFV (los que creé en el Paso 1.5), y uso "Añadir a pantalla de inicio". A partir de ahí se actualiza sola con Canvas cada 4 horas, y también se refresca ella sola en el móvil en cuanto publico algún cambio en el código — no hace falta que la cierre ni la vuelva a añadir.

## Qué asignaturas sincroniza

No mantengo ninguna lista a mano: en cada sincronización, el robot le pregunta a Canvas qué asignaturas tengo marcadas con la ⭐ de favorito en el dashboard, y trae las tareas y avisos de esas — todas las que sean. Si algún cuatrimestre no tengo ninguna marcada, trae todas las activas como respaldo. Para que una asignatura nueva empiece a aparecer, solo tengo que marcarla con la estrella en Canvas; en la siguiente sincronización (máximo 4 horas, o antes si fuerzo el robot a mano) ya sale sola, sin tocar ni una línea de código.
