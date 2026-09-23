# Cuadrante (versión independiente)

App de tareas y avisos de Canvas que corre sola, gratis, sin depender de ninguna
suscripción de Claude. Se sincroniza cada 4 horas mediante un robot de GitHub
(GitHub Actions) y guarda los datos en una base de datos gratuita (Firebase).

## Qué vas a crear (todo gratis)

1. Un proyecto de **Firebase** → guarda tus tareas/avisos y controla quién entra.
2. Un repositorio de **GitHub** → aloja la web y ejecuta la sincronización sola.
3. La web publicada con **GitHub Pages** → el enlace que abres en el móvil.

## Paso 1 — Crear el proyecto Firebase

1. Ve a [console.firebase.google.com](https://console.firebase.google.com) → **Crear un proyecto** (dale el nombre que quieras, ej. "cuadrante").
2. En el menú de la izquierda, entra en **Firestore Database** → **Crear base de datos** → modo producción → la ubicación te da igual (elige `eur3` si quieres que esté en Europa).
3. Cuando esté creada, ve a la pestaña **Reglas** y pega el contenido del archivo `firestore.rules` de esta carpeta, sustituyendo lo que haya. Pulsa **Publicar**.
4. En el menú de la izquierda, entra en **Authentication** → **Comenzar** → pestaña **Sign-in method** → activa **Google**.
5. Ve al icono de engranaje (arriba a la izquierda) → **Configuración del proyecto** → baja hasta "Tus apps" → pulsa el icono `</>` (web) → dale un nombre → **Registrar app**. Te muestra un bloque `firebaseConfig = {...}` — copia esos valores.
6. Abre `index.html` de esta carpeta, busca `const firebaseConfig = {` (cerca de la línea 260) y sustituye los valores `"TU_..."` por los que acabas de copiar. Guarda.

## Paso 2 — Clave para que el robot pueda escribir

1. En Firebase, **Configuración del proyecto** → pestaña **Cuentas de servicio** → **Generar nueva clave privada**. Se descarga un archivo `.json` — guárdalo, lo necesitas en el Paso 4 (no lo subas nunca a GitHub directamente).

## Paso 3 — Crear el repositorio en GitHub

1. En [github.com](https://github.com), crea un repositorio nuevo, **público** (ej. "cuadrante"). Tiene que ser público porque GitHub Pages (Paso 5) no funciona con repositorios privados en la cuenta gratuita — no pasa nada por ello: tu token de Canvas y las credenciales de Firebase nunca van en el código, viajan aparte como "secretos" cifrados (Paso 4) que nadie puede leer ni descargar, y tus tareas/avisos reales viven en Firestore protegidos por `firestore.rules`, que solo deja pasar a tu email. Lo único visible para cualquiera sería el código en sí, no tus datos.
2. Sube TODOS los archivos de esta carpeta (`index.html`, `sync_canvas.py`, `firestore.rules`, la carpeta `.github/`) — puedes arrastrarlos en la web de GitHub con "Add file → Upload files", o con `git` si lo conoces.

## Paso 4 — Añadir tus secretos al repositorio

En el repositorio → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, crea estos tres:

| Nombre exacto | Valor |
|---|---|
| `CANVAS_DOMAIN` | `ufv-es.instructure.com` |
| `CANVAS_TOKEN` | tu token de acceso personal de Canvas (el mismo que le diste a Claude, o genera uno nuevo) |
| `FIREBASE_CREDENTIALS` | abre el `.json` del Paso 2 con un editor de texto y pega **todo su contenido** tal cual |

## Paso 5 — Publicar la web con GitHub Pages

1. En el repositorio → **Settings** → **Pages**.
2. En "Source" elige **Deploy from a branch**, rama `main`, carpeta `/ (root)` → **Save**.
3. Espera un minuto y GitHub te da un enlace tipo `https://tu-usuario.github.io/cuadrante/` — esa es tu app.

## Paso 6 — Probar la sincronización

1. En el repositorio → pestaña **Actions** → verás el workflow "Sincronizar Canvas" → pulsa **Run workflow** para probarlo ahora mismo en vez de esperar 4 horas.
2. Si falla, el propio log de GitHub Actions te dice la línea exacta del error (normalmente un secreto mal copiado).

## Paso 7 — Instalarla en el móvil

Abre el enlace de GitHub Pages en tu teléfono, inicia sesión con tu cuenta de Google de la UFV, y usa "Añadir a pantalla de inicio". A partir de ahí se actualiza sola cada 4 horas, sin que tengas que abrir nada ni depender de Claude.

## Si cambias de cuatrimestre

Las nuevas asignaturas tendrán otros `course_id` de Canvas. Para sacarlos, pega esto en la barra de tu navegador (sustituyendo TU_TOKEN):

```
https://ufv-es.instructure.com/api/v1/courses?enrollment_state=active&per_page=100&access_token=TU_TOKEN
```

Y actualiza el diccionario `COURSE_MAP` al principio de `sync_canvas.py` con los `id` y `name` que veas, y vuelve a subir el archivo a GitHub.
