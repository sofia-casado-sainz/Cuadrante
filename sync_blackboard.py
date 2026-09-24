#!/usr/bin/env python3
"""
Sincroniza el calendario de Blackboard (UAH) con Firestore.
Es el robot "hermano" de sync_canvas.py: mismo Firestore, misma app, pero escribe
en el espacio de datos de OTRA persona (la de la UAH), así que cada una ve solo lo suyo.

Variables de entorno necesarias:
  BLACKBOARD_ICS_URL   la URL secreta de "suscribirse" del calendario de Blackboard
                        (empieza por https://xxx.blackboard.com/webapps/calendar/calendarFeed/...)
  FIREBASE_CREDENTIALS el JSON completo de la cuenta de servicio de Firebase (como texto)
  VAPID_PRIVATE_KEY    opcional, para avisos push
"""

import os
import re
import json
import sys
import hashlib
from datetime import datetime, date, time as dtime, timezone
from zoneinfo import ZoneInfo

import requests
import firebase_admin
from firebase_admin import credentials, firestore
from pywebpush import webpush, WebPushException
from icalendar import Calendar

BLACKBOARD_ICS_URL = os.environ["BLACKBOARD_ICS_URL"]

# El email con el que esta persona inicia sesión en la app (el que le creaste en
# Firebase Authentication). Este robot escribe SOLO en users/{OWNER_EMAIL}/... — la otra
# persona (UFV) nunca ve estos datos y esta persona nunca ve los de Canvas.
OWNER_EMAIL = "ana.ecenarro@edu.uah.es"

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_CLAIMS_SUB = f"mailto:{OWNER_EMAIL}"
APP_URL = "https://sofia-casado-sainz.github.io/cuadrante/"

MADRID = ZoneInfo("Europe/Madrid")

# ---------------------------------------------------------------------------
# Blackboard no deja consultar "qué asignaturas tienes en favoritos" por API,
# así que a diferencia de Canvas esta lista NO se actualiza sola. Si cambias
# de cuatrimestre o de favoritos, actualiza aquí el código (lo que sale debajo
# de la imagen de cada curso, tipo "APY6L26") y el nombre bonito para mostrar.
# ---------------------------------------------------------------------------
COURSE_MAP = {
    "APY6L26": "Conmutación",
    "8WQD726": "Electrónica de potencia",
    "3L4M626": "Instrumentación electrónica",
    "L731026": "Sistemas electrónicos digitales avanzados",
    "YC66326": "Sistemas electrónicos para comunicaciones",
    "64H5426": "Tecnologías de alta frecuencia",
    "2Y55126": "TFG. Actividades transversales. Ingeniería",
}


def user_ref(db):
    """Documento raíz del dueño de este script dentro de Firestore (users/{email})."""
    return db.collection("users").document(OWNER_EMAIL)


def clean_title(title):
    title = re.sub(r"\s*\[[^\]]*\]\s*$", "", title or "").strip()
    # quita el prefijo de curso académico tipo "2026-27: " si lo lleva
    title = re.sub(r"^\d{4}-\d{2}:\s*", "", title).strip()
    return title


def match_course(component):
    """Busca el código de la asignatura (p.ej. APY6L26) en los campos del evento
    para saber de qué asignatura es, en vez de adivinarlo por el texto."""
    fields = ("SUMMARY", "DESCRIPTION", "CATEGORIES", "LOCATION", "UID")
    haystack = " ".join(str(component.get(f) or "") for f in fields)
    for code, name in COURSE_MAP.items():
        if code in haystack:
            return name
    return ""


def split_course_title(summary):
    """Respaldo para eventos donde no se reconoce el código: intenta separar
    'Asignatura: Título' por los separadores típicos."""
    summary = clean_title(summary)
    for sep in (":", " - ", "–"):
        if sep in summary:
            course, _, title = summary.partition(sep)
            course, title = course.strip(), title.strip()
            if course and title:
                return course, title
    return "", summary


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

    def update(self, ref, data):
        self.batch.update(ref, data)
        self._maybe_flush()

    def commit(self):
        if self.pending:
            self.batch.commit()
            self.pending = 0


def fetch_ics():
    """Descarga el feed .ics. La URL es secreta (funciona como una contraseña), así que
    nunca se imprime ni se guarda en ningún sitio."""
    resp = requests.get(BLACKBOARD_ICS_URL, timeout=30)
    resp.raise_for_status()
    return resp.content


def event_datetime(value):
    """Un VEVENT de icalendar puede traer un 'date' (evento de todo el día) o un
    'datetime' con hora. Normaliza ambos a un datetime con zona horaria de Madrid."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=MADRID)
        return value.astimezone(MADRID)
    if isinstance(value, date):
        return datetime.combine(value, dtime(23, 59), tzinfo=MADRID)
    return None


def sync_blackboard_calendar(db):
    raw = fetch_ics()
    cal = Calendar.from_ical(raw)

    events_coll = user_ref(db).collection("tasks")
    existing = {d.id: d.to_dict() for d in events_coll.stream()}

    batch = ChunkedBatch(db)
    count = 0
    new_count = 0
    new_events = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for component in cal.walk("VEVENT"):
        uid = str(component.get("UID") or "")
        if not uid:
            continue
        doc_id = "bb-" + hashlib.md5(uid.encode("utf-8")).hexdigest()[:16]

        raw_summary = str(component.get("SUMMARY") or "(sin título)")
        course = match_course(component)
        if course:
            title = clean_title(raw_summary)
            if title.strip().lower() == course.strip().lower():
                title = course
        else:
            course, title = split_course_title(raw_summary)
            print(f"(sin asignatura reconocida) {raw_summary!r}", file=sys.stderr)

        dtstart = component.get("DTSTART")
        due_dt = event_datetime(dtstart.dt) if dtstart else None
        due_at = due_dt.astimezone(timezone.utc).isoformat() if due_dt else None

        url_prop = component.get("URL")
        url = str(url_prop) if url_prop else ""

        ref = events_coll.document(doc_id)
        count += 1

        if doc_id in existing:
            batch.update(ref, {
                "title": title,
                "course": course,
                "due_at": due_at,
                "url": url,
                "updated_at": now_iso,
            })
        else:
            new_count += 1
            new_events.append({"title": title, "course": course})
            batch.set(ref, {
                "title": title,
                "course": course,
                "due_at": due_at,
                "url": url,
                "type": "blackboard",
                "source": "blackboard",
                "done": False,
                "updated_at": now_iso,
            })

    batch.set(user_ref(db).collection("meta").document("sync"), {
        "tasks_last_sync": now_iso,
        "tasks_found": count,
    }, merge=True)
    batch.commit()
    print(f"Blackboard: {count} eventos procesados, {new_count} nuevos.")
    return new_events


def send_push_to_all(db, title, body, url):
    """Manda un aviso push a todos los dispositivos suscritos por el dueño de este script."""
    if not VAPID_PRIVATE_KEY:
        return
    subs = list(user_ref(db).collection("pushSubscriptions").stream())
    if not subs:
        return
    payload = json.dumps({"title": title, "body": body, "url": url})
    for sdoc in subs:
        s = sdoc.to_dict() or {}
        sub_info = {"endpoint": s.get("endpoint"), "keys": s.get("keys", {})}
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_SUB},
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                sdoc.reference.delete()
            else:
                print(f"Aviso: no se pudo mandar push a {sdoc.id}: {e}", file=sys.stderr)


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    new_events = sync_blackboard_calendar(db)

    if new_events:
        body = ", ".join(e["title"] for e in new_events[:5])
        if len(new_events) > 5:
            body += f" y {len(new_events) - 5} más"
        send_push_to_all(db, f"📅 {len(new_events)} evento(s) nuevo(s)", body, APP_URL)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"Error descargando el calendario de Blackboard: {e}", file=sys.stderr)
        sys.exit(1)