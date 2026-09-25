#!/usr/bin/env python3
"""
Genera la newsletter semanal con IA (Gemini, gratis) y la guarda en Firestore,
en newsletter/actual — un único documento compartido que se SOBRESCRIBE cada
semana (no es un catálogo que crece, es "la newsletter de esta semana"), así
que la ven igual todas las personas que usen la app.

Es el "agente" semanal: lo lanza solo el workflow generate-newsletter.yml
(GitHub Actions, cron los lunes), pero también se puede lanzar a mano desde
la pestaña Actions → "Run workflow" si quieres una newsletter nueva ya mismo.

OJO — límite importante: esto llama a la API normal de Gemini (generateContent),
que NO navega por internet ni busca noticias reales de esta semana — escribe
con lo que ya sabe de su entrenamiento. Así que esto no es un resumen de
titulares de hoy, es más bien una newsletter de divulgación: explicaciones,
tendencias de fondo y curiosidades de IA/tecnología, no última hora. Si en
algún momento quieres noticias realmente actuales, haría falta añadir una
fuente de noticias de verdad (un feed RSS, una API de noticias) en vez de
pedírselo directamente a Gemini.

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


def pedir_newsletter_a_gemini():
    hoy = datetime.now(timezone.utc).strftime("%d de %B de %Y")
    prompt = f"""Escribe el contenido de una newsletter semanal de divulgación, en español de
España, para una persona joven universitaria interesada en tecnología. Hoy es
{hoy} (úsalo solo de referencia de estación del año / contexto, no finjas que
tienes noticias de última hora de hoy mismo, porque no las tienes).

Escribe:
- Un "resumen" de 1-2 frases dando la bienvenida a la newsletter de esta semana.
- Exactamente 5 "items", uno de cada una de estas categorías, en este orden:
  1. ia — algo interesante y bien explicado sobre inteligencia artificial (un
     concepto, una tendencia de fondo, una aplicación práctica)
  2. informatica — algo de informática/tecnología en general (programación,
     ciberseguridad, hardware, internet)
  3. politica — un tema de actualidad política EXPLICADO DE FORMA NEUTRA,
     presentando el contexto sin tomar partido
  4. mundo — algo interesante sobre el mundo en general (ciencia, sociedad,
     cultura, economía)
  5. curiosidad — un dato curioso, sorprendente y verificado

Cada item lleva un "titulo" corto (máximo 8 palabras) y un "texto" de 2-3
frases, claro y ameno, sin tecnicismos innecesarios. Dado que no tienes acceso
a internet, evita inventarte hechos MUY recientes o cifras concretas que
podrías tener mal — prefiere explicar conceptos, tendencias de fondo o datos
que sean estables en el tiempo, y sé honesto/genérico antes que inventar."""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "resumen": {"type": "STRING"},
                    "items": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "categoria": {"type": "STRING"},
                                "titulo": {"type": "STRING"},
                                "texto": {"type": "STRING"},
                            },
                        },
                    },
                },
            },
            "temperature": 0.9,
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

    contenido = pedir_newsletter_a_gemini()
    items = [it for it in contenido.get("items", []) if it.get("titulo") and it.get("texto")]

    db.collection("newsletter").document("actual").set({
        "fecha": datetime.now(timezone.utc).isoformat(),
        "resumen": contenido.get("resumen", ""),
        "items": items,
    })

    print(f"Newsletter guardada con {len(items)} secciones.")


if __name__ == "__main__":
    try:
        main()
    except (requests.exceptions.RequestException, RuntimeError) as e:
        print(f"Error llamando a la API de Gemini: {e}", file=sys.stderr)
        sys.exit(1)