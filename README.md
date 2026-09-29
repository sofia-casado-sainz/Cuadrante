# Cuadrante

Panel personal de tareas, avisos, horario y agenda diaria, sincronizado solo
desde Canvas o Blackboard. Corre gratis, sin ninguna suscripción de pago, y
sin depender de que nadie lo mantenga a mano día a día — un conjunto de
"robots" (GitHub Actions) lo hace todo solo, cada hora.

## Qué es esto (y qué no es)

Esto es una **ayuda personal, para organizarme yo y un grupo de amigas de la
carrera**. No tiene ningún otro fin por ahora: no es un producto, no está
pensado para publicarse ni para que lo use gente fuera de este grupo, y no
guarda ni comparte datos de nadie que no haya sido invitada expresamente
(creando su cuenta a mano, como se explica más abajo). Cada persona ve solo
sus propias tareas, avisos y horario — lo único que se comparte entre todas
es la racha de retos (a propósito, para verla entre amigas) y el catálogo de
retos/newsletter, que no son datos personales de nadie.

## Qué problema resuelve

Canvas (UFV) y Blackboard (UAH) tienen sus propias apps y páginas, pero cada
una hay que abrirla por separado, y ninguna te deja ver "todo lo que tengo
que entregar" ni "mi horario de la semana" de un vistazo, ni avisarte con una
notificación en el móvil. Cuadrante junta tareas + avisos + horario + una
agenda diaria en una sola pantalla, igual para todas las que la usan, cada
una viendo solo lo suyo.

## Cómo funciona por dentro

Son 4 piezas, todas con capa gratuita:

1. **Firebase** (de Google) — hace dos cosas:
   - **Firestore**: la base de datos. Todo lo que ves en la app (tareas,
     avisos, horario, rachas...) vive ahí, organizado en `users/{tu-email}/...`
     — cada persona solo puede leer y escribir dentro de su propia carpeta
     (lo impone `firestore.rules`, no la app, así que no se puede saltar
     desde el móvil de nadie).
   - **Authentication**: controla quién puede entrar a la app (email +
     contraseña). Es una cuenta aparte, que tú creas a mano para cada
     persona — no tiene por qué coincidir con ninguna contraseña real de
     la universidad.
2. **GitHub Pages** — aloja `index.html` (la app entera: una sola página web)
   en un enlace público gratuito, que se abre desde el móvil como cualquier
   web y se puede "Añadir a pantalla de inicio" para que se sienta como una
   app normal (esto es lo que se llama una PWA).
3. **GitHub Actions** — son los "robots": scripts en Python que GitHub
   ejecuta solos, con un horario (cron), sin que nadie tenga que darle a
   nada. Cada uno hace una cosa:

   | Robot (archivo) | Qué hace | Cuándo |
   |---|---|---|
   | `sync_canvas.py` | Trae tareas y avisos de Canvas, para cada persona de UFV | cada hora |
   | `sync_blackboard.py` | Lo mismo, pero de Blackboard (UAH), leyendo el feed de calendario | cada hora |
   | `generate_agenda.py` | Con IA, escribe una frase de "qué hacer hoy" por cada tarea pendiente | cada mañana, 6:00 UTC |
   | `generate_newsletter.py` | Con IA, escribe una newsletter semanal de tecnología/IA (compartida) | lunes, 7:00 UTC |
   | `generate_cursos.py` | Con IA, sugiere cursos/certificaciones gratis según la carrera de cada una | día 1 de mes, 8:00 UTC |
   | `generate_retos.py` | Con IA, añade ~20 retos nuevos al catálogo compartido, sin repetir | día 1 de mes, 9:00 UTC |
   | `seed_retos.py` | Siembra el catálogo de retos la primera vez (o lo reemplaza si se pide) | solo a mano, cuando se lanza |
   | `migrate_to_users.py` | Uso único: migró los datos sueltos de Sofía al modelo multi-persona | ya no hace falta |

4. **Google Gemini** (opcional, gratis) — la IA que usan Agenda, Newsletter,
   Cursos y Retos. Si algún día no quieres esa parte, esos 4 robots
   simplemente no se activan (necesitan la clave `GEMINI_API_KEY`); el resto
   de la app (tareas, avisos, horario) funciona igual sin ella.

## Funcionalidades

- **Tareas**: todo lo pendiente de tus asignaturas, con fecha de entrega,
  enlace directo a Canvas/Blackboard, y opción de marcar hecho o añadir
  tareas propias a mano.
- **Avisos**: anuncios de tus profesores (solo Canvas — Blackboard no trae
  este tipo de anuncios, así que a esa cuenta no le aparece la pestaña).
- **Horario**: tu horario semanal de clases, con hora, aula y color por
  asignatura (el desplegable de asignaturas se calcula solo, a partir de tus
  propias tareas/avisos ya sincronizados — cada persona ve las suyas, nunca
  las de otra). Se puede marcar una clase como "solo esta semana" (para algo
  puntual, que no se repite) y añadir varios días a la vez sin repetir el
  formulario.
- **Agenda**: una IA te resume cada mañana qué hacer hoy con lo pendiente, y
  avisa por push si algo vence mañana y sigue sin marcarse hecho.
- **Retos**: un reto de hábito saludable al día (con humor, para que apetezca
  hacerlo), con una racha (🔥 días seguidos) que se compara entre todas las
  personas que usan la app, no solo la tuya.
- **Calendario, Newsletter y Cursos sugeridos**: vistas auxiliares, ya
  explicadas en la tabla de robots de arriba.
- **Notificaciones push**: activables desde la propia app ("🔔 Activar
  avisos"), independientes por persona y por dispositivo.
- **Accesibilidad**: los colores de asignaturas se ajustan automáticamente
  para leerse bien tanto en fondo claro como oscuro (contraste WCAG).

---

## Manual 1 — Instalación desde cero

Esto se hace **una sola vez**, al montar la app por primera vez.

### Paso 1 — Proyecto de Firebase

1. Ve a [console.firebase.google.com](https://console.firebase.google.com) → **Crear un proyecto**.
2. **Firestore Database** → **Crear base de datos** → modo producción → la ubicación da igual (`eur3` si la quieres en Europa).
3. Pestaña **Reglas** → pega el contenido de `firestore.rules` de esta carpeta → **Publicar**.
4. **Authentication** → **Comenzar** → pestaña **Sign-in method** → activa **Correo electrónico/contraseña** (no "Google").
5. Pestaña **Users** → **Add user** por cada persona que vaya a usar la app: su email + una contraseña de arranque (luego cada una puede cambiarla ella misma, ver más abajo).
6. Icono de engranaje → **Configuración del proyecto** → "Tus apps" → icono `</>` (web) → **Registrar app**. Copia el bloque `firebaseConfig = {...}`.
7. En `index.html`, busca `const firebaseConfig = {` y sustituye los valores por los tuyos.

### Paso 2 — Clave para que los robots puedan escribir

**Configuración del proyecto** → pestaña **Cuentas de servicio** → **Generar nueva clave privada** → se descarga un `.json`. Guárdalo (nunca lo subas a GitHub directamente, va como secreto en el Paso 4).

### Paso 3 — Repositorio de GitHub

1. Crea un repositorio nuevo, **público** (GitHub Pages gratis lo exige). No pasa nada: los tokens y credenciales nunca van en el código, viajan como "secretos" cifrados que nadie puede leer, y tus datos reales viven en Firestore, protegidos por `firestore.rules`.
2. Sube todos los archivos de esta carpeta.

### Paso 4 — Secretos del repositorio

**Settings → Secrets and variables → Actions → New repository secret**:

| Nombre exacto | Valor |
|---|---|
| `CANVAS_DOMAIN` | `ufv-es.instructure.com` |
| `CANVAS_USERS` | JSON `{"email@alumnos.ufv.es": "su_token", ...}` — uno por cada persona de UFV (ver Manual 2) |
| `BLACKBOARD_ICS_URL` | la URL de "suscribirse" del calendario de Blackboard de la persona de la UAH (esta sí es una URL, a diferencia del token de Canvas — ver el aviso más abajo) |
| `FIREBASE_CREDENTIALS` | todo el contenido del `.json` del Paso 2, tal cual |
| `VAPID_PRIVATE_KEY` | opcional, para notificaciones push |
| `GEMINI_API_KEY` | opcional, clave gratis de [aistudio.google.com/apikey](https://aistudio.google.com/apikey), para Agenda/Newsletter/Cursos/Retos |

> ⚠️ **Canvas y Blackboard usan credenciales DISTINTAS, no las confundas** (esto nos pasó de verdad, ver Manual 3): en **Canvas** hace falta un **token de acceso personal** (una cadena larga, se saca en Cuenta → Configuración → Claves de acceso → Nueva clave de acceso). En **Blackboard** en cambio se usa la **URL del feed de calendario** (la de "suscribirse", que sí empieza por `https://...`). Cada plataforma es distinta.

### Paso 5 — GitHub Pages

**Settings → Pages** → Source: **Deploy from a branch**, rama `main`, carpeta `/ (root)` → **Save**. En un minuto tienes el enlace `https://tu-usuario.github.io/cuadrante/`.

### Paso 6 — Probar

Pestaña **Actions** → "Sincronizar Canvas" → **Run workflow**, para probarlo ya en vez de esperar a la próxima hora en punto. Si falla, el log de esa ejecución dice la línea exacta del error (ver Manual 3 para los fallos típicos).

### Paso 7 — Instalarla en el móvil

Abre el enlace en el móvil, inicia sesión con el email/contraseña que le creaste en el Paso 1.5, y "Añadir a pantalla de inicio". A partir de ahí se actualiza sola.

---

## Manual 2 — Añadir una persona nueva

Esto sí se repite, cada vez que se una alguien al grupo. Necesitas 3 cosas
suyas: su **token de Canvas**, su **email**, y decidir una **contraseña** de
arranque para ella.

1. **Su token de Canvas** (ella lo saca desde su propia cuenta, tú no puedes
   hacerlo por ella): Canvas → icono de su cuenta → **Configuración** →
   sección **Claves de acceso aprobadas** → **+ Nueva clave de acceso** → le
   pone un nombre (p. ej. "Cuadrante") y **Generar clave**. Canvas la enseña
   **una sola vez** — hay que copiarla ahí mismo.

2. **Añádela al secreto `CANVAS_USERS`** (Settings → Secrets and variables →
   Actions → `CANVAS_USERS` → **Update**), con su email como clave:

```json
   {
     "mi_email@alumnos.ufv.es": "tu_token",
     "email_nueva_persona@alumnos.ufv.es": "su_token"
   }
```

   Todas las líneas menos la última llevan coma al final. **Nunca** pegues
   estos tokens en un chat ni en ningún otro sitio — solo aquí, en el
   secreto.

3. **Añade su email a `index.html`** (tres listas, todas cerca de la línea
   410): `ALLOWED_EMAILS`, `UNIVERSIDAD` (pon `"UFV"`) y `PLATAFORMA` (pon
   `"Canvas"`). Puedes pedírmelo a mí directamente — el email no es un dato
   sensible, así que sí me lo puedes decir (el token nunca).

4. **Créale la cuenta de acceso a la app**: Firebase Console → tu proyecto →
   **Authentication** → **Users** → **Add user** → su email + una
   contraseña de arranque cualquiera. En cuanto entre por primera vez, puede
   ponerse la suya propia desde el enlace "¿Olvidaste tu contraseña?" de la
   pantalla de login (le llega un correo con un enlace de Firebase para
   elegirla ella misma).

5. **Opcional** — si quieres que le lleguen sugerencias de cursos
   personalizadas (pestaña Cursos), añade su email a `PERFILES` en
   `generate_cursos.py`, con su universidad y carrera.

6. Prueba: **Actions → Sincronizar Canvas → Run workflow**. Si sale ✓ verde,
   ya puede entrar en la app con su email y la contraseña que le diste.

---

## Manual 3 — Problemas que nos hemos encontrado (y cómo se arreglaron)

Un registro de los líos reales que han salido montando y ampliando esto,
para no volver a perder tiempo si se repiten.

- **El botón "Activar avisos" no se quedaba activado** entre una apertura de
  la app y la siguiente (sobre todo en iPhone). Causa: se comprobaba con
  `getRegistration()`, que a veces devuelve "nada" recién abierta la app
  aunque la suscripción exista de verdad. Arreglo: usar `register()` (que no
  falla si ya existía) y volver a comprobar el estado cada vez que se cambia
  de pestaña dentro de la app.

- **El desplegable de "Asignatura" en Horario era una lista fija**, escrita
  a mano con las 9 asignaturas de la primera persona. Al añadir gente de
  otras carreras, a ellas no les aparecía ninguna de las suyas. Arreglo: el
  desplegable se calcula solo, por persona, a partir de sus propias tareas y
  avisos ya sincronizados (y de lo que ya tenga en su Horario) — cada una ve
  las suyas.

- **La racha de retos solo comparaba a dos personas** (tú y "la otra"), a
  propósito de cuando la app era solo para dos. Al llegar más gente, dejó de
  tener sentido. Arreglo: ahora es una lista que se ordena sola por racha
  (más días arriba), y crece automáticamente con cada persona que se añada a
  `ALLOWED_EMAILS` — no hay que tocar nada al añadir gente nueva.

- **Pasar de una sola cuenta de Canvas a varias**: el robot `sync_canvas.py`
  estaba escrito para UN solo token y UN solo email, fijos en el propio
  código. Se rediseñó para leer una lista de personas (`CANVAS_USERS`, un
  JSON `email → token`) y sincronizar a cada una por separado, sin que el
  fallo de una (p. ej. un token caducado) impida sincronizar a las demás.

- **Error de JSON al crear `CANVAS_USERS`**: faltaba una coma entre dos
  personas del JSON. El propio error de Python (`Expecting ',' delimiter:
  line X`) señala la línea exacta — hay que revisar que todas las líneas
  lleven coma al final excepto la última, y que las comillas sean rectas
  (`"`), no las curvas que a veces pone el móvil solo.

- **Se confundió el token de Canvas con la URL del calendario (`.ics`)**:
  son credenciales distintas. La URL del calendario sirve para suscribir un
  calendario externo (o para Blackboard, que sí funciona así), pero la API
  de Canvas necesita un token de acceso personal de verdad (ver Manual 2,
  paso 1). Canvas devuelve `401 Unauthorized` si le mandas la URL en vez del
  token.

- **`Quota exceeded` (código 429) de Firestore**: el plan gratuito (Spark)
  tiene un límite fijo *por día* (50.000 lecturas, 20.000 escrituras,
  20.000 borrados). La causa real no era el número de personas, sino que el
  robot **reescribía todas las tareas y avisos en cada sincronización**,
  aunque no hubiera cambiado nada — con 5 personas sincronizando cada hora,
  eso solo ya rozaba las 20.000 escrituras diarias. Arreglo: ahora compara
  cada tarea/aviso con lo que ya había guardado, y **se salta la escritura
  si no ha cambiado nada real** — en la práctica, esto reduce el gasto en
  más del 90%. Si algún día se volviera a rozar el límite (por ejemplo con
  muchas más personas), la solución sería pasar el proyecto de Firebase al
  plan **Blaze** (pago por uso): sigue siendo gratis hasta las mismas
  cantidades de arriba, solo que en vez de bloquearse de golpe al llegar al
  límite, cobra el exceso (para un grupo de amigas es prácticamente
  imposible que llegue a costar nada real, pero conviene poner una alerta de
  presupuesto de 1€ por si acaso).

- **El menú de pestañas se cortaba en pantallas pequeñas** (móvil, tablet) y
  había que desplazarlo para ver todas las opciones. Arreglo: las pestañas
  ahora pasan a una segunda fila si no caben (`flex-wrap`), en vez de
  obligar a hacer scroll horizontal.

- **La hora de fin de una clase se podía dejar antes que la de inicio** en
  Horario, y solo se avisaba con un mensaje después de intentar guardar.
  Arreglo: al poner la hora de inicio, la de fin se rellena sola media hora
  más tarde, y el propio campo ya no deja escribir (ni pegar) una hora
  anterior a la de inicio.

- **Colores poco legibles** en algunos fondos (texto negro sobre un color
  oscuro elegido a mano, por ejemplo). Arreglo: el texto sobre cada bloque
  de color se calcula solo (negro o blanco, el que dé más contraste), y los
  colores de pastillas/puntos se ajustan automáticamente para cumplir el
  contraste mínimo de accesibilidad (WCAG) tanto en modo claro como oscuro.

- **No había forma de cambiar la contraseña** una vez creada la cuenta —
  había que pedírselo a quien administra la app. Arreglo: enlace "¿Olvidaste
  tu contraseña?" en la pantalla de login, que manda un correo de
  restablecimiento de Firebase; cada persona puede elegir la suya sin
  depender de nadie.

- **Los retos eran demasiado "serios"** (consejos de bienestar estándar).
  Se rehízo el catálogo con un tono gracioso/autoparódico que sigue
  escondiendo un hábito saludable de verdad detrás del chiste, y se dejó un
  mecanismo seguro (con confirmación explícita) para reemplazar el catálogo
  entero de una vez si hiciera falta, en vez de solo poder añadir.

## Si cambias de cuatrimestre

Ya no hace falta tocar nada a mano: cada sincronización pregunta sola a
Canvas qué asignaturas tienes marcadas con la estrella de favorito ese
cuatrimestre (o todas las activas si no has marcado ninguna), así que las
asignaturas nuevas aparecen solas. Esto era manual antes (había que editar
un `COURSE_MAP` a mano); ya no.

## Mantenimiento general

- Los tokens y claves solo se guardan como secretos de GitHub — nunca en el
  código, nunca en un chat.
- Si alguien deja de usar la app: quítala de `ALLOWED_EMAILS` en
  `index.html`, bórrala de `CANVAS_USERS` (o `BLACKBOARD_ICS_URL` si era la
  cuenta de UAH), y borra su usuario en Firebase Authentication. Sus datos
  en Firestore (`users/su-email/...`) se pueden dejar o borrar a mano, como
  se prefiera.
- Cualquier cambio de código en este repositorio (`index.html`, los `.py`,
  los `.yml`) hay que subirlo a GitHub para que tenga efecto — nada de esto
  se actualiza solo.
