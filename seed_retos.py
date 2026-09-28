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

# (categoria, texto) — frases cortas, graciosas, con un emoji delante. La broma es el
# envoltorio; por dentro cada una esconde algo que de verdad ayuda a despejarse,
# relajarse o crear un hábito saludable (moverse, respirar, dormir mejor, desconectar
# del móvil, comer mejor, socializar, estudiar mejor...).
SEED_RETOS = [
    # --- mañana ---
    ("manana", "🕺 Baila como si fueras famosa mientras se hace el café"),
    ("manana", "🎤 Cántale a tu reflejo en el espejo como si fuera tu público"),
    ("manana", "🦸 Ponte una capa imaginaria antes de salir de casa, aunque nadie lo sepa"),
    ("manana", "🐸 Da tres saltos de rana nada más levantarte para despertar el cuerpo"),
    ("manana", 'Saluda a alguien como si fueras de otra época: "buenos días tenga usted" 🎩'),
    ("manana", "🥱 Bosteza exageradamente 5 veces seguidas — es contagioso y relaja la mandíbula"),
    ("manana", "🧦 Ponte los calcetines más ridículos que tengas para arrancar el día sonriendo"),
    ("manana", "☕ Bébete el café fingiendo que eres una crítica gastronómica muy exigente"),
    # --- movimiento ---
    ("movimiento", "🕺 Baila una canción entera como si nadie te viera (aunque te vea el gato)"),
    ("movimiento", "🚶 Camina imitando el andar de un personaje famoso durante un minuto"),
    ("movimiento", "🦆 Haz el paseo del pato hasta la cocina, aunque parezca ridículo"),
    ("movimiento", 'Haz el "baile de la victoria" aunque hoy no hayas ganado nada todavía 🏆'),
    ("movimiento", "🥊 Da cuatro puñetazos al aire, como si boxearas contra el estrés del día"),
    ("movimiento", "🐒 Estírate como un mono perezoso durante 2 minutos entre clase y clase"),
    ("movimiento", "🧹 Haz playback con una escoba de micrófono con tu canción más animada"),
    ("movimiento", "🐢 Muévete a cámara lenta un minuto entero, como una tortuga zen"),
    # --- alimentación ---
    ("alimentacion", 'Preséntate a tu fruta antes de comértela: "hola, manzana, hoy te toca a ti" 🍎'),
    ("alimentacion", "👨‍🍳 Cocina algo nuevo poniéndote un delantal imaginario de chef con estrella Michelin"),
    ("alimentacion", "🍫 Saboréa un trozo de chocolate a cámara lenta, como en un anuncio de tele"),
    ("alimentacion", "🥤 Bebe un vaso de agua brindando contigo misma por haber llegado hasta aquí"),
    ("alimentacion", "🍽️ Come hoy con la mano contraria a la que usas siempre, y ríete del resultado"),
    ("alimentacion", "🍌 Ponle una vocecilla graciosa a tu snack antes de comértelo, como si hablara"),
    ("alimentacion", "🍉 Corta la fruta en formas raras, como si fueras repostera de concurso de tele"),
    ("alimentacion", "🫖 Prepárate una infusión y bébetela despacio fingiendo que eres de la realeza"),
    # --- sueño ---
    ("sueno", "🐑 Cuenta ovejas con nombres absurdos hasta quedarte frita"),
    ("sueno", 'Ponte calcetines calentitos y decláralos oficialmente tu "uniforme de dormir" 🧦'),
    ("sueno", "🧸 Duerme con un peluche o algo blandito cerca, aunque tengas 20 años"),
    ("sueno", "🌧️ Pon sonidos de lluvia y finge que estás de acampada en vez de en tu cuarto"),
    ("sueno", '📵 Manda tu móvil "a dormir" a otra habitación y deséale buenas noches en voz alta'),
    ("sueno", "🏰 Haz un fuerte con las mantas 2 minutos antes de dormir en serio"),
    ("sueno", "😴 Cuéntale a la almohada tres cosas buenas del día antes de dormir"),
    ("sueno", 'Baja la temperatura de tu cuarto y decláralo oficialmente "modo cueva relax" 🌡️'),
    # --- mente / mindfulness ---
    ("mente", "🤪 Ponte caras raras frente al espejo hasta que te entre la risa"),
    ("mente", "🎂 Respira hondo 5 veces imaginando que soplas las velas de un cumpleaños gigante"),
    ("mente", "🎭 Narra tu día como si fuera el tráiler de una peli muy dramática, en broma"),
    ("mente", "🥔 Medita 3 minutos imaginando que eres una patata sin ninguna responsabilidad"),
    ("mente", "🛏️ Grita bajito dentro de una almohada todo lo que hoy te frustró"),
    ("mente", "🎈 Imagina tus preocupaciones como globos y suéltalas una a una, mentalmente"),
    ("mente", "🤡 Haz de payaso contigo misma: ríete de algo que hoy te salió mal"),
    ("mente", "🐌 Haz algo hoy a cámara lenta a propósito, solo por el gusto de ir sin prisa"),
    # --- digital ---
    ("digital", "🌿 Habla con una planta en vez de mirar el móvil, aunque no te conteste"),
    ("digital", "📴 Métete el móvil en un cajón y finge que se ha ido de vacaciones"),
    ("digital", "🐌 Contesta un mensaje mañana en vez de ahora mismo: practica la lentitud"),
    ("digital", "🎲 Cambia 20 minutos de scroll por un juego de mesa o de cartas, aunque sea solo/a"),
    ("digital", '✈️ Pon el móvil en modo avión y date un "viaje" mental de 15 minutos sin él'),
    ("digital", "✏️ Cambia 15 minutos de redes por garabatear sin sentido en un papel"),
    ("digital", 'Hazte una foto rara (no "bonita") y ponla de fondo de pantalla un rato 🤳'),
    # --- social ---
    ("social", "🎭 Imita a alguien famoso delante de un amigo y que adivine quién es"),
    ("social", "🎤 Manda un audio cantando en vez de escribir un mensaje aburrido"),
    ("social", 'Da un abrazo random a alguien y dile: "necesitaba practicar mi abrazo semanal" 🫂'),
    ("social", "😂 Cuenta el chiste más malo que sepas a la primera persona que veas"),
    ("social", "👟 Felicita a alguien por algo sin importancia, como lo bien que lleva los cordones"),
    ("social", "📸 Manda una foto ridícula tuya a un amigo, sin ninguna razón aparente"),
    ("social", '🗣️ Inventa un idioma random y "habla" con un amigo un minuto entero'),
    # --- estudio / productividad ---
    ("estudio", "🍅 Estudia 25 minutos y celebra el descanso con un bailecito de 30 segundos"),
    ("estudio", "🧙 Explícate a ti misma lo que acabas de estudiar con voz de sabio o sabia"),
    ("estudio", "🥇 Date una medalla imaginaria cada vez que termines una tarea pesada"),
    ("estudio", "🎬 Escribe tus apuntes de hoy fingiendo que eres una influencer explicándolo en vídeo"),
    ("estudio", "🧸 Explícale lo que has estudiado a un peluche o a la pared, en voz alta"),
    ("estudio", "🏆 Haz un pequeño baile de la victoria por cada entrega que termines hoy"),
    # --- autocuidado ---
    ("autocuidado", "🎤 Date una ducha cantando como si fuera un concierto solo para ti"),
    ("autocuidado", "🖼️ Dibuja algo horrible a propósito y cuélgalo con orgullo un rato"),
    ("autocuidado", "📺 Ponte crema hidratante narrando como si fueras un anuncio de televisión"),
    ("autocuidado", "🪞 Baila delante del espejo evaluándote a ti misma como jurado de talent show"),
    ("autocuidado", "🎤 Haz un mini concierto usando el cepillo del pelo de micrófono"),
    ("autocuidado", "🎉 Celebra con confeti imaginario cualquier cosa pequeña que hayas conseguido hoy"),
    ("autocuidado", "🧖 Ponte una mascarilla facial y siéntete una diva random durante un rato"),
    # --- aire libre / naturaleza ---
    ("aire_libre", "☁️ Sal a la calle y ponle nombre a la primera nube rara que veas"),
    ("aire_libre", 'Silba o haz ruiditos a un pájaro y espera a ver si "te contesta" 🐦'),
    ("aire_libre", "🍃 Persigue una hoja que vuele con el viento unos segundos, como si fueras niña"),
    ("aire_libre", "🌧️ Sal a que te caigan cuatro gotas de lluvia sin correr a resguardarte"),
    ("aire_libre", "🌻 Huele la primera flor random que te encuentres por la calle"),
    ("aire_libre", "🐿️ Busca un animal por la calle (perro, gato, pájaro) y salúdalo mentalmente"),
    ("aire_libre", "☁️ Túmbate un rato a mirar las nubes y busca formas raras en ellas"),
    # --- varios ---
    ("varios", "🎲 Deja que una moneda decida algo pequeño hoy (qué comer, qué ruta tomar)"),
    ("varios", "🧦 Ponte los calcetines del revés un rato a ver si notas la diferencia"),
    ("varios", "🎭 Habla con acento random todo el día con la gente de confianza"),
    ("varios", "🛝 Haz la croqueta por el suelo de tu cuarto, aunque sea solo un segundo"),
    ("varios", "🎤 Grábate cantando fatal una canción y ríete al escucharte después"),
    ("varios", "🎁 Regálate algo pequeño y gratis hoy: 10 minutos de nada, una canción, un chiste"),
    ("varios", "🃏 Inventa una palabra nueva hoy y cuélasela a alguien en una frase"),
    ("varios", 'Convierte una tarea aburrida en un reto de circo: "a ver si lo hago sin quejarme" 🎪'),
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


# Como cada reto nuevo tiene un ID distinto (calculado a partir de su propio texto),
# volver a sembrar con textos NUEVOS no toca los retos de antes: se quedarían los dos
# a la vez. Para cambiar del todo el catálogo (por ejemplo, pasar de retos serios a
# graciosos) hay que borrar antes los que ya había. Por seguridad esto NO se hace solo:
# hay que activarlo a propósito con BORRAR_CATALOGO_ANTERIOR=si (hay una casilla para
# esto en GitHub Actions al lanzar el workflow a mano).
BORRAR_ANTERIORES = os.environ.get("BORRAR_CATALOGO_ANTERIOR", "no").strip().lower() in ("si", "sí", "true", "1", "yes")


def borra_catalogo_actual(db):
    coll = db.collection("retos")
    docs = list(coll.stream())
    batch = db.batch()
    pendientes = 0
    for d in docs:
        batch.delete(d.reference)
        pendientes += 1
        if pendientes >= 400:  # límite de Firestore por batch: 500
            batch.commit()
            batch = db.batch()
            pendientes = 0
    if pendientes:
        batch.commit()
    return len(docs)


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    if BORRAR_ANTERIORES:
        borrados = borra_catalogo_actual(db)
        print(f"BORRAR_CATALOGO_ANTERIOR estaba activado: borrados {borrados} retos del catálogo anterior.")

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