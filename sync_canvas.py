#!/usr/bin/env python3
"""
Sincroniza tareas y avisos de Canvas con Firestore.
Pensado para correr desde GitHub Actions con un cron, pero funciona igual en local.

Variables de entorno necesarias:
  CANVAS_DOMAIN        ej. "ufv-es.instructure.com"
  CANVAS_TOKEN          tu token de acceso personal de Canvas
  FIREBASE_CREDENTIALS  el JSON completo de la cuenta de servicio de Firebase (como texto)
"""

import os
import re
import json
import html
import sys
from datetime import datetime, timedelta, timezone

import requests
import firebase_admin
from firebase_admin import credentials, firestore

# Tus 9 asignaturas: course_id de Canvas -> nombre bonito.
# Si cambias de cuatrimestre, actualiza este diccionario con los IDs nuevos
# (los sacas de https://<tu-canvas>/api/v1/courses?enrollment_state=active&access_token=TU_TOKEN
# pegado en la barra del navegador, o preguntándoselo a Claude una vez).
COURSE_MAP = {
    "course_74819": "Computación de alto rendimiento",
    "course_70061": "Aprendizaje estadístico y data mining",
    "course_70107": "Emprendimiento e innovación",
    "course_70168": "Internet of Things",
    "course_70027": "Ingeniería del Software II",
    "course_70126": "La cuestión de Dios",
    "course_70212": "Planificación y gestión de proyectos informáticos",
    "course_73690": "Roboética en el cuidado de la salud",
    "course_73399": "Seguridad",
}

DOMAIN = os.environ["CANVAS_DOMAIN"]
TOKEN = os.environ["CANVAS_TOKEN"]
BASE = f"https://{DOMAIN}/api/v1"
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {TOKEN}"})


def get_all_pages(url, params=None):
    """Sigue la paginación de Canvas (cabecera Link) y devuelve todos los resultados."""
    items = []
    while url:
        resp = SESSION.get(url, params=params, timeout=30)
        resp.raise_for_status()
        items.extend(resp.json())
        params = None  # los parámetros ya van en la URL "next"
        url = None
        link = resp.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1 : part.find(">")]
    return items


def strip_html(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500] + ("…" if len(text) > 500 else "")


def clean_title(title):
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", title or "").strip()


class ChunkedBatch:
    """Wrapper around Firestore batches that auto-commits every N writes
    (Firestore caps a batch at 500 operations)."""

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

    def update(self, ref, data):
        self.batch.update(ref, data)
        self._maybe_flush()

    def commit(self):
        if self.pending:
            self.batch.commit()
            self.pending = 0


def sync_tasks(db):
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=14)).isoformat()
    end = (today + timedelta(days=180)).isoformat()

    items = get_all_pages(
        f"{BASE}/planner/items",
        params={"per_page": 100, "start_date": start, "end_date": end},
    )

    existing = {d.id: d.to_dict() for d in db.collection("tasks").stream()}

    batch = ChunkedBatch(db)
    count = 0
    new_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for it in items:
        ptype = it.get("plannable_type")
        if ptype not in ("assignment", "quiz", "discussion_topic"):
            continue
        course_key = f"course_{it.get('course_id')}"
        if course_key not in COURSE_MAP:
            continue

        plannable = it.get("plannable") or {}
        plannable_id = it.get("plannable_id")
        doc_id = f"t-{ptype}-{plannable_id}"
        title = clean_title(plannable.get("title") or plannable.get("name") or "(sin título)")
        due_at = it.get("plannable_date")
        url = it.get("html_url", "")
        submitted = bool((it.get("submissions") or {}).get("submitted"))

        ref = db.collection("tasks").document(doc_id)
        count += 1

        if doc_id in existing:
            update = {
                "title": title,
                "due_at": due_at,
                "url": url,
                "course": COURSE_MAP[course_key],
                "updated_at": now_iso,
            }
            if submitted:
                update["done"] = True
            batch.update(ref, update)
        else:
            new_count += 1
            batch.set(ref, {
                "title": title,
                "course": COURSE_MAP[course_key],
                "due_at": due_at,
                "url": url,
                "type": ptype,
                "source": "canvas",
                "done": submitted,
                "updated_at": now_iso,
            })

    batch.set(db.collection("meta").document("sync"), {
        "tasks_last_sync": now_iso,
        "tasks_found": count,
    }, merge=True)
    batch.commit()
    print(f"Tareas: {count} procesadas, {new_count} nuevas.")

# (fin sync_tasks)


def sync_avisos(db):
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=60)).isoformat()

    params = [("per_page", 100), ("start_date", start)]
    for course_key in COURSE_MAP:
        params.append(("context_codes[]", course_key))

    items = get_all_pages(f"{BASE}/announcements", params=params)

    existing_ids = {d.id for d in db.collection("avisos").stream()}

    batch = ChunkedBatch(db)
    count = 0
    new_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for it in items:
        aviso_id = it.get("id")
        doc_id = f"a-{aviso_id}"
        course_key = it.get("context_code", "")
        course = COURSE_MAP.get(course_key, "")

        ref = db.collection("avisos").document(doc_id)
        count += 1
        data = {
            "title": it.get("title", "(sin título)"),
            "message": strip_html(it.get("message", "")),
            "course": course,
            "url": it.get("html_url", ""),
            "posted_at": it.get("posted_at"),
        }

        if doc_id in existing_ids:
            batch.update(ref, data)
        else:
            new_count += 1
            data["leido"] = False
            data["updated_at"] = now_iso
            batch.set(ref, data)

    batch.set(db.collection("meta").document("sync"), {
        "avisos_last_sync": now_iso,
        "avisos_found": count,
    }, merge=True)
    batch.commit()
    print(f"Avisos: {count} procesados, {new_count} nuevos.")


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    sync_tasks(db)
    sync_avisos(db)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"Error llamando a Canvas: {e}", file=sys.stderr)
        sys.exit(1)
