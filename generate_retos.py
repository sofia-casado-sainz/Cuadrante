#!/usr/bin/env python3
"""
Genera retos nuevos con IA (Gemini, gratis) y los añade al catálogo compartido
de Firestore (colección retos/), sin tocar los que ya existen ni repetir
ninguno (ni literalmente ni parafraseado, hasta donde se le puede pedir a la IA).

Es el "agente" mensual: lo lanza solo el workflow generate-retos.yml (GitHub
Actions, cron una vez al mes), pero también se puede lanzar a mano desde la
pestaña Actions → "Run workflow" si quieres más retos ya mismo.

Variables de entorno necesarias:
  GEMINI_API_KEY        clave gratuita de https://aistudio.google.com/apikey
  FIREBASE_CREDENTIALS  el JSON completo de la cuenta de servicio de Firebase (como texto)

Variables opcionales:
  RETOS_A_GENERAR       cuántos retos nuevos pedir cada vez (por defecto 20)
"""

import os
import re
import sys
import json
import hashlib
import unicodedata
from datetime import datetime, timezone

import requests
import firebase_admin
from firebase_admin import credentials, firestore

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

RETOS_A_GENERAR = int(os.environ.get("RETOS_A_GENERAR", "20"))


class ChunkedBatch:
    """Igual que en sync_canvas.py: auto-commitea cada N escrituras (límite de Firestore: 500)."""

    def __init__(self, db, chunk_size=400):
        self.db = db
        self.chunk_size = chunk_size
        self.batch = db.batch()
        self.pending = 0

    def _maybe_flush(self):
        self.pending += 1
        if self.pending >= self.chunk_size:
            self.batch.commit()
            self.batch = self.db.batch()
            self.pending = 0

    def set(self, ref, data, merge=False):
        self.batch.set(ref, data, merge=merge)
        self._maybe_flush()

    def commit(self):
        if self.pending:
            self.batch.commit()
            self.pending = 0


def normaliza(texto):
    """Quita emoji, acentos, mayúsculas y espacios de sobra, para comparar solo el
    contenido y no crear un reto "nuevo" que en realidad es el mismo con otra palabra."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    solo_letras = re.sub(r"[^a-zA-Z0-9\s]", " ", sin_acentos)
    return re.sub(r"\s+", " ", solo_letras).strip().lower()


def reto_id(texto):
    return "r-" + hashlib.md5(normaliza(texto).encode("utf-8")).hexdigest()[:16]


def cargar_catalogo_actual(db):
    docs = list(db.collection("retos").stream())
    return [d.to_dict().get("texto", "") for d in docs if d.to_dict().get("texto")]


def pedir_retos_a_gemini(existentes, cuantos):
    # Con las últimas ~200 basta para que Gemini no repita; mandar miles no aporta nada.
    lista_existente = "\n".join(f"- {t}" for t in existentes[-200:])

    prompt = f"""Genera {cuantos} retos de hábitos saludables, en español de España, pensados
para una persona universitaria. Cada reto debe:
- ser una frase corta (máximo 15 palabras), en imperativo o muy directa
- empezar por UN emoji que encaje con el contenido
- ser concreto y realizable en un solo día
- cubrir temas variados: movimiento, alimentación, sueño, mente/mindfulness, uso del
  móvil y redes sociales, estudio/productividad, relaciones sociales, autocuidado,
  naturaleza

No repitas, ni siquiera parafraseado, ninguno de estos retos que ya existen en el catálogo:
{lista_existente}

Devuelve solo el array JSON de strings pedido, nada más."""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {"type": "ARRAY", "items": {"type": "STRING"}},
            "temperature": 1.0,
        },
    }
    resp = requests.post(GEMINI_URL, params={"key": GEMINI_API_KEY}, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    try:
        texto_json = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Respuesta inesperada de Gemini: {json.dumps(data)[:500]}")
    return json.loads(texto_json)


def guarda_retos_nuevos(db, candidatos, existentes_normalizados):
    coll = db.collection("retos")
    batch = ChunkedBatch(db)
    now_iso = datetime.now(timezone.utc).isoformat()
    anadidos = []

    for texto in candidatos:
        texto = (texto or "").strip()
        if not texto:
            continue
        norm = normaliza(texto)
        if not norm or norm in existentes_normalizados:
            continue  # ya existía, o es un duplicado dentro de esta misma tanda
        existentes_normalizados.add(norm)
        batch.set(coll.document(reto_id(texto)), {
            "texto": texto,
            "fuente": "gemini",
            "creado": now_iso,
        })
        anadidos.append(texto)

    batch.commit()
    return anadidos


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    existentes = cargar_catalogo_actual(db)
    existentes_normalizados = {normaliza(t) for t in existentes if t}
    print(f"Catálogo actual: {len(existentes)} retos.")

    candidatos = pedir_retos_a_gemini(existentes, RETOS_A_GENERAR)
    print(f"Gemini propuso {len(candidatos)} retos.")

    anadidos = guarda_retos_nuevos(db, candidatos, existentes_normalizados)
    print(f"Añadidos {len(anadidos)} retos nuevos al catálogo:")
    for t in anadidos:
        print(f"  {t}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"Error llamando a la API de Gemini: {e}", file=sys.stderr)
        sys.exit(1)