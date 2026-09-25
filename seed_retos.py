#!/usr/bin/env python3
"""
Script de UN SOLO USO. Siembra el catálogo compartido de "retos" (hábitos
saludables) en Firestore, en la colección retos/ (no depende de ningún
usuario concreto: la ven todas las personas que usen la app).

Es seguro ejecutarlo más de una vez: cada reto se guarda con un ID calculado
a partir de su propio texto, así que repetirlo simplemente vuelve a escribir
lo mismo encima, nunca duplica nada.

A partir de aquí, el catálogo va creciendo solo cada mes con generate_retos.py
(que usa IA para inventar retos nuevos sin repetir los que ya hay).

Variables de entorno necesarias:
  FIREBASE_CREDENTIALS  el JSON completo de la cuenta de servicio de Firebase (como texto)
"""

import os
import re
import json
import hashlib
import unicodedata
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

# (categoria, texto) — frases cortas, en imperativo, con un emoji delante.
SEED_RETOS = [
    # --- mañana ---
    ("manana", "🌅 Despiértate 15 minutos antes y no mires el móvil hasta vestirte"),
    ("manana", "🛏️ Haz la cama nada más levantarte"),
    ("manana", "💧 Bebe un vaso de agua antes del café"),
    ("manana", "🧘 Dedica 3 minutos a respirar hondo antes de empezar el día"),
    ("manana", "☀️ Abre la ventana y deja entrar luz natural en cuanto te levantes"),
    ("manana", "📝 Escribe las 3 cosas más importantes que quieres lograr hoy"),
    ("manana", "🚿 Termina la ducha con 10 segundos de agua fría"),
    ("manana", "🧴 Ponte crema solar aunque el plan de hoy sea quedarte en casa"),
    ("manana", "🎵 Elige la música o el silencio con intención, no por costumbre"),
    ("manana", "🙏 Piensa en algo que agradeces antes de salir de casa"),
    # --- movimiento ---
    ("movimiento", "🚶 Camina al menos 20 minutos de un tirón hoy"),
    ("movimiento", "🪜 Sube las escaleras en vez del ascensor todo el día"),
    ("movimiento", "🧍 Levántate y estira cada hora si estudias sentado/a"),
    ("movimiento", "🚴 Ve en bici o andando a algún sitio al que sueles ir en coche o bus"),
    ("movimiento", "🤸 Haz 10 minutos de estiramientos antes de dormir"),
    ("movimiento", "💪 Haz una tabla corta de fuerza: flexiones, sentadillas, plancha"),
    ("movimiento", "🕺 Baila una canción entera, sin más excusa que apetecerte"),
    ("movimiento", "📱 Camina mientras hablas por teléfono en vez de quedarte sentado/a"),
    ("movimiento", "🧗 Prueba un tipo de ejercicio que nunca hayas hecho"),
    ("movimiento", "🌳 Haz tu paseo o ejercicio de hoy al aire libre en vez de en un gimnasio"),
    # --- alimentación ---
    ("alimentacion", "🥗 Añade una ración extra de verdura a una de tus comidas"),
    ("alimentacion", "🍎 Cambia un snack procesado por fruta hoy"),
    ("alimentacion", "🍳 Desayuna algo con proteína en vez de solo hidratos"),
    ("alimentacion", "🍽️ Come sin pantallas delante, prestando atención a lo que comes"),
    ("alimentacion", "🥤 Sustituye un refresco por agua o infusión"),
    ("alimentacion", "🍱 Prepara tu comida de mañana hoy, en vez de improvisar"),
    ("alimentacion", "🍫 Si comes algo dulce, saboréalo despacio en vez de con prisa"),
    ("alimentacion", "🛒 Haz la compra con una lista para evitar picoteo impulsivo"),
    ("alimentacion", "🍌 Lleva contigo un snack saludable para no caer en la máquina expendedora"),
    ("alimentacion", "🥦 Prueba una verdura o receta que no sueles comer"),
    # --- sueño ---
    ("sueno", "😴 Apaga las pantallas 30 minutos antes de dormir"),
    ("sueno", "🌙 Acuéstate a la misma hora que ayer, sin alargar la noche"),
    ("sueno", "☕ No tomes cafeína después de las 5 de la tarde"),
    ("sueno", "📵 Deja el móvil cargando fuera del alcance de la cama"),
    ("sueno", "📖 Lee unas páginas en papel antes de dormir en vez de mirar el móvil"),
    ("sueno", "🌡️ Baja un poco la temperatura de tu cuarto antes de acostarte"),
    ("sueno", "⏰ Pon la alarma con margen para no empezar el día corriendo"),
    ("sueno", "🧘 Haz 5 minutos de relajación o respiración antes de apagar la luz"),
    # --- mente / mindfulness ---
    ("mente", "🧠 Escribe 5 minutos en un diario, sin pensar en cómo suena"),
    ("mente", "🌬️ Prueba una respiración de 4-7-8 cuando notes tensión"),
    ("mente", "🚫 Pasa un rato sin quejarte de nada, ni en voz alta ni en tu cabeza"),
    ("mente", "🎯 Elige una sola tarea y hazla sin multitarea durante media hora"),
    ("mente", "🖼️ Observa algo con atención total durante 2 minutos, sin juzgarlo"),
    ("mente", "💭 Anota un pensamiento negativo y escribe una versión más justa de él"),
    ("mente", "🕯️ Date 10 minutos de silencio total, sin música ni notificaciones"),
    ("mente", "🌟 Anota tres cosas que te salieron bien hoy antes de dormir"),
    ("mente", "🤍 Háblate hoy como le hablarías a un amigo"),
    ("mente", "🧩 Haz algo solo por diversión, sin que tenga que ser \"productivo\""),
    # --- digital ---
    ("digital", "📵 Pasa 2 horas seguidas sin mirar redes sociales"),
    ("digital", "🔕 Desactiva las notificaciones de una app que te distraiga"),
    ("digital", "⏳ Usa un temporizador y limita el móvil a 30 minutos fuera de tareas necesarias"),
    ("digital", "📴 Deja el móvil en otra habitación mientras estudias"),
    ("digital", "🖤 Prueba el modo blanco y negro en el móvil un rato para que enganche menos"),
    ("digital", "📸 Vive un momento hoy sin sacar el móvil para grabarlo"),
    ("digital", "🗑️ Borra una app que uses solo para matar el tiempo"),
    ("digital", "💻 Cierra todas las pestañas que no estés usando ahora mismo"),
    # --- social ---
    ("social", "📞 Llama a alguien en vez de mandarle un mensaje"),
    ("social", "🤗 Da las gracias a alguien de forma específica y sincera"),
    ("social", "👂 Escucha a alguien sin mirar el móvil ni interrumpir"),
    ("social", "✉️ Escribe a un amigo con el que hace tiempo que no hablas"),
    ("social", "🍽️ Come con alguien en vez de solo/a, si puedes elegir"),
    ("social", "🎁 Haz un pequeño favor a alguien sin que te lo pida"),
    ("social", "💬 Pregunta a alguien cómo está de verdad, y espera la respuesta"),
    ("social", "🫂 Da un abrazo a alguien hoy"),
    ("social", "📝 Escribe una nota o mensaje bonito a alguien, sin motivo especial"),
    ("social", "🙌 Pide ayuda con algo en vez de intentar hacerlo todo solo/a"),
    # --- estudio / productividad ---
    ("estudio", "📚 Estudia una hora con el móvil en otra habitación"),
    ("estudio", "🍅 Prueba la técnica Pomodoro: 25 minutos de foco, 5 de descanso"),
    ("estudio", "🗂️ Organiza tu escritorio o tu carpeta de apuntes antes de empezar"),
    ("estudio", "✅ Haz la tarea que más pereza te da la primera, no la última"),
    ("estudio", "🎯 Fíjate un único objetivo claro para la sesión de estudio de hoy"),
    ("estudio", "📅 Planifica mañana antes de acostarte hoy"),
    ("estudio", "🧹 Deja tu mesa de estudio despejada al terminar"),
    ("estudio", "🔁 Repasa algo de hace una semana en vez de solo lo de hoy"),
    ("estudio", "🙅 Di que no a una distracción concreta durante tu tiempo de estudio"),
    ("estudio", "🏁 Termina algo que tenías a medias antes de empezar algo nuevo"),
    # --- autocuidado ---
    ("autocuidado", "🛁 Date un momento de cuidado personal sin prisa"),
    ("autocuidado", "🎨 Dedica 15 minutos a algo creativo sin objetivo ninguno"),
    ("autocuidado", "🧴 Hidrata tu piel después de ducharte"),
    ("autocuidado", "💸 Revisa un gasto pequeño de esta semana y decide si de verdad lo necesitabas"),
    ("autocuidado", "🧺 Ordena un rincón pequeño de tu cuarto que llevaba tiempo pendiente"),
    ("autocuidado", "🕰️ Date permiso para no hacer nada 10 minutos, sin culpa"),
    ("autocuidado", "🎶 Descubre una canción o artista nuevo hoy"),
    ("autocuidado", "🧽 Limpia tu móvil o tu teclado, que los tocas todo el día"),
    # --- aire libre / naturaleza ---
    ("aire_libre", "🌳 Pasa al menos 15 minutos al aire libre hoy, sin móvil"),
    ("aire_libre", "🌄 Sal a que te dé la luz de la mañana en la cara unos minutos"),
    ("aire_libre", "🍃 Fíjate en tres cosas de la naturaleza que veas de camino a algún sitio"),
    ("aire_libre", "🪴 Cuida una planta, aunque sea regarla y mirar cómo está"),
    ("aire_libre", "🌦️ Sal fuera un momento aunque haga el tiempo que haga"),
    ("aire_libre", "🏞️ Elige una ruta distinta a la habitual para pasear o ir a clase"),
    # --- varios ---
    ("varios", "💧 Lleva una botella de agua contigo todo el día"),
    ("varios", "🧦 Prepara la ropa del día siguiente antes de dormir"),
    ("varios", "📔 Escribe una meta pequeña para esta semana"),
    ("varios", "🎧 Escucha un podcast o audiolibro en vez de música de fondo hoy"),
    ("varios", "🚯 Recoge y tira algo de basura que veas por la calle"),
    ("varios", "🧠 Aprende una palabra nueva y úsala en una frase hoy"),
]


def normaliza(texto):
    """Quita emoji, acentos, mayúsculas y espacios de sobra, para poder comparar
    solo el contenido del reto (lo mismo que hace generate_retos.py)."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    solo_letras = re.sub(r"[^a-zA-Z0-9\s]", " ", sin_acentos)
    return re.sub(r"\s+", " ", solo_letras).strip().lower()


def reto_id(texto):
    return "r-" + hashlib.md5(normaliza(texto).encode("utf-8")).hexdigest()[:16]


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    coll = db.collection("retos")
    now_iso = datetime.now(timezone.utc).isoformat()

    batch = db.batch()
    for categoria, texto in SEED_RETOS:
        ref = coll.document(reto_id(texto))
        batch.set(ref, {
            "texto": texto,
            "categoria": categoria,
            "fuente": "seed",
            "creado": now_iso,
        }, merge=True)
    batch.commit()

    print(f"Sembrados {len(SEED_RETOS)} retos en la colección 'retos' de Firestore.")


if __name__ == "__main__":
    main()