#!/usr/bin/env python3
"""
Script de UN SOLO USO. Copia tus datos actuales (guardados sueltos en Firestore:
tasks, avisos, schedule, settings/colors, meta/sync, pushSubscriptions) al nuevo
espacio personal users/{OWNER_EMAIL}/..., para que no se pierda nada al pasar la
app al modelo multi-usuario.

No borra nada de lo viejo (por si algo sale mal, puedes repetirlo tranquilamente).

Después de comprobar que la app funciona bien con el nuevo index.html, puedes
borrar este archivo y el workflow migrate.yml — ya no hacen falta.
"""

import os
import json
import sys

import firebase_admin
from firebase_admin import credentials, firestore

OWNER_EMAIL = "9206029@alumnos.ufv.es"

FLAT_COLLECTIONS = ["tasks", "avisos", "schedule", "pushSubscriptions"]
FLAT_DOCS = [("settings", "colors"), ("meta", "sync")]


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    user_root = db.collection("users").document(OWNER_EMAIL)
    total = 0

    for coll_name in FLAT_COLLECTIONS:
        docs = list(db.collection(coll_name).stream())
        for d in docs:
            user_root.collection(coll_name).document(d.id).set(d.to_dict())
            total += 1
        print(f"{coll_name}: {len(docs)} documento(s) copiados.")

    for coll_name, doc_id in FLAT_DOCS:
        snap = db.collection(coll_name).document(doc_id).get()
        if snap.exists:
            user_root.collection(coll_name).document(doc_id).set(snap.to_dict())
            total += 1
            print(f"{coll_name}/{doc_id}: copiado.")
        else:
            print(f"{coll_name}/{doc_id}: no existía, se salta.")

    print(f"\nListo. {total} documento(s) copiados a users/{OWNER_EMAIL}/...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error durante la migración: {e}", file=sys.stderr)
        sys.exit(1)