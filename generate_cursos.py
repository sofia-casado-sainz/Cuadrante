#!/usr/bin/env python3
"""
Genera sugerencias de cursos/certificaciones gratuitas con IA (Gemini, gratis),
una lista distinta para cada persona según su carrera, y las guarda en
Firestore en users/{email}/cursos/actual (un documento por persona, que se
SOBRESCRIBE cada vez — no es un catálogo que crece, es "las sugerencias de
ahora mismo").

Es el "agente" mensual: lo lanza solo el workflow generate-cursos.yml (GitHub
Actions, cron el día 1 de cada mes), pero también se puede lanzar a mano desde
la pestaña Actions → "Run workflow" si quieres sugerencias nuevas ya mismo.

Para añadir a una persona nueva, añade su email al diccionario PERFILES de
abajo con su universidad y carrera, y sube este archivo otra vez.

OJO: igual que con la newsletter, Gemini no navega por internet, así que no
inventa enlaces directos a cursos concretos (podrían no existir o estar
rotos) — sugiere plataformas y cursos/certificaciones reales y conocidas por
su nombre, para que los busques tú mismo/a en esa plataforma.

Variables de entorno necesarias:
  GEMINI_API_KEY        clave gratuita de https://aistudio.google.com/apikey
  FIREBASE_CREDENTIALS  el JSON completo de la cuenta de servicio de Firebase (como texto)
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

import requests
import firebase_admin
from firebase_admin import credentials, firestore

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def llamar_gemini(body, intentos=3):
    """POST a Gemini con reintentos: a veces tarda más de la cuenta o hay un
    corte de red pasajero entre el runner de GitHub Actions y la API de
    Google, y no merece la pena que falle el robot entero por eso."""
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            resp = requests.post(GEMINI_URL, params={"key": GEMINI_API_KEY}, json=body, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            ultimo_error = e
            if intento < intentos:
                espera = 10 * intento
                print(f"Intento {intento}/{intentos} falló ({e}); reintento en {espera}s…", file=sys.stderr)
                time.sleep(espera)
    raise ultimo_error

# Añade aquí a cada persona que use la app, con su universidad y carrera:
PERFILES = {
    "9206029@alumnos.ufv.es": {
        "universidad": "UFV",
        "carrera": "Ingeniería Informática, con diploma en IA aplicada a la robótica",
    },
    "ana.ecenarro@edu.uah.es": {
        "universidad": "UAH",
        "carrera": "Ingeniería de Telecomunicaciones",
    },
}


def pedir_cursos_a_gemini(carrera):
    prompt = f"""Sugiere 5 cursos o certificaciones GRATUITAS y reales (de plataformas
conocidas como Coursera, edX, freeCodeCamp, Google, Microsoft Learn, AWS
Skill Builder, Kaggle Learn, LinkedIn Learning, etc.) para una persona que
estudia {carrera}, pensados para añadir como certificación en su perfil de
LinkedIn.

Para cada uno, da:
- "plataforma": el nombre de la plataforma
- "nombre": el nombre real del curso o certificación (no te lo inventes; si
  no estás seguro del nombre exacto, da el nombre del área/track más conocido
  de esa plataforma en ese tema)
- "por_que": una frase corta de por qué encaja con esta carrera

No incluyas URLs (podrían no ser correctas) — con el nombre y la plataforma
basta para buscarlo."""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "plataforma": {"type": "STRING"},
                        "nombre": {"type": "STRING"},
                        "por_que": {"type": "STRING"},
                    },
                },
            },
            "temperature": 0.8,
        },
    }
    data = llamar_gemini(body)
    try:
        texto_json = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Respuesta inesperada de Gemini: {json.dumps(data)[:500]}")
    return json.loads(texto_json)


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    for email, perfil in PERFILES.items():
        try:
            candidatos = pedir_cursos_a_gemini(perfil["carrera"])
            sugerencias = [
                c for c in candidatos
                if c.get("plataforma") and c.get("nombre")
            ]
            db.collection("users").document(email).collection("cursos").document("actual").set({
                "fecha": datetime.now(timezone.utc).isoformat(),
                "universidad": perfil["universidad"],
                "carrera": perfil["carrera"],
                "sugerencias": sugerencias,
            })
            print(f"[{email}] {len(sugerencias)} cursos guardados.")
        except (requests.exceptions.RequestException, RuntimeError) as e:
            print(f"[{email}] Error pidiendo cursos a Gemini: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()