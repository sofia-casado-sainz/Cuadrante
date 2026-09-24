#!/usr/bin/env python3
"""
Sincroniza el calendario de Blackboard (UAH) con Firestore.
Es el robot "hermano" de sync_canvas.py: mismo Firestore, misma app, pero escribe
en el espacio de datos de OTRA persona (la de la UAH), así que cada una ve solo lo suyo.

Cómo asocia cada evento con su asignatura (Blackboard no da esto por API como Canvas):
  1. TITLE_MAP: título exacto del evento -> asignatura. Se ha construido a mano
     mirando la página "Actividad" de Blackboard, que sí muestra la asignatura de
     cada entrega (el feed del calendario no la trae para casi ningún evento).
  2. COURSE_MAP: si el título no está en TITLE_MAP, busca alguno de los códigos de
     curso (p.ej. "APY6L26") en los campos del evento - esto solo funciona para los
     eventos "de cabecera" del curso, que sí llevan el código.
  3. Si ninguna de las dos encuentra nada, se avisa en el log con
     "(sin asignatura reconocida)" y se guarda igualmente, sin asignatura, usando el
     método antiguo de separar por ":" o "-" como último recurso.

Variables de entorno necesarias:
  BLACKBOARD_ICS_URL   la URL secreta de "suscribirse" del calendario de Blackboard
                        (empieza por https://xxx.blackboard.com/webapps/calendar/calendarFeed/...)
  FIREBASE_CREDENTIALS el JSON completo de la cuenta de servicio de Firebase (como texto)
  VAPID_PRIVATE_KEY    opcional, para avisos push
  DEBUG_EVENTS          opcional, número de eventos de los que volcar TODOS los campos
                        en el log (para depurar). 0 = no volcar nada (por defecto).
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

OWNER_EMAIL = "ana.ecenarro@edu.uah.es"

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_CLAIMS_SUB = f"mailto:{OWNER_EMAIL}"
APP_URL = "https://sofia-casado-sainz.github.io/cuadrante/"

MADRID = ZoneInfo("Europe/Madrid")

DEBUG_EVENTS = int(os.environ.get("DEBUG_EVENTS", "0") or "0")

# Códigos de curso de Blackboard -> nombre bonito. Solo sirve para los eventos "de
# cabecera" que sí llevan el código en algún campo. Hay que revisarlo cada cuatrimestre.
COURSE_MAP = {
    "APY6L26": "Conmutación",
    "8WQD726": "Electrónica de potencia",
    "3L4M626": "Instrumentación electrónica",
    "L731026": "Sistemas electrónicos digitales avanzados",
    "YC66326": "Sistemas electrónicos para comunicaciones",
    "64H5426": "Tecnologías de alta frecuencia",
    "2Y55126": "TFG. Actividades transversales. Ingeniería",
}

# Título exacto del evento (en minúsculas) -> asignatura. Construido a mano a partir
# de la página "Actividad" de Blackboard. Si un título nuevo no aparece aquí, cae en
# COURSE_MAP o se queda sin asignatura (y se avisa en el log para poder añadirlo).
TITLE_MAP = {
    # Sistemas electrónicos digitales avanzados (L731026)
    "pei1-serie": "Sistemas electrónicos digitales avanzados",
    "pei2-dsp": "Sistemas electrónicos digitales avanzados",
    "pei1-tempadcdma": "Sistemas electrónicos digitales avanzados",
    "pei1-ejec": "Sistemas electrónicos digitales avanzados",
    "pei1-state": "Sistemas electrónicos digitales avanzados",
    "calificacion de teoría": "Sistemas electrónicos digitales avanzados",
    "pei2-http": "Sistemas electrónicos digitales avanzados",
    "pei2-mem": "Sistemas electrónicos digitales avanzados",
    "calificación de laboratorio": "Sistemas electrónicos digitales avanzados",
    "pei2-rtos": "Sistemas electrónicos digitales avanzados",
    "actividad voluntaria de máquinas de estado": "Sistemas electrónicos digitales avanzados",
    "tp - múltiplex": "Sistemas electrónicos digitales avanzados",  # sin confirmar del todo

    # Sistemas electrónicos para comunicaciones (YC66326)
    "p4": "Sistemas electrónicos para comunicaciones",
    "p3": "Sistemas electrónicos para comunicaciones",
    "práctica 1.2 (entrega opcional) - resonador tdk r820 - respuesta en frecuencia": "Sistemas electrónicos para comunicaciones",
    "práctica 0 - curso aplac": "Sistemas electrónicos para comunicaciones",
    "práctica 1 - componentes pasivos en af - comparativas respuesta en frecuencia": "Sistemas electrónicos para comunicaciones",
    "entrega práctica final: emisora fm - explicación y especificaciones": "Sistemas electrónicos para comunicaciones",
    "práctica 4.1 - amplificadores en rf - pequeña señal": "Sistemas electrónicos para comunicaciones",
    "entrega práctica final: emisora fm - convocatoria extraordinaria": "Sistemas electrónicos para comunicaciones",
    "práctica 2 - simular transmisor fm práctica final en bloques (sistemas)": "Sistemas electrónicos para comunicaciones",
    "práctica 3 - adaptación de impedancias": "Sistemas electrónicos para comunicaciones",
    "prácticas 1 y 2": "Sistemas electrónicos para comunicaciones",

    # Tecnologías de alta frecuencia (64H5426)
    "notas de memoria de práctica 1": "Tecnologías de alta frecuencia",
    "notas de memoria de práctica 2": "Tecnologías de alta frecuencia",
    "consulta notas de laboratorio 2025-2026": "Tecnologías de alta frecuencia",
    "problemas adaptación": "Tecnologías de alta frecuencia",
    "adaptación de impedancias": "Tecnologías de alta frecuencia",

    # Instrumentación electrónica (3L4M626)
    "pei 1": "Instrumentación electrónica",
}


def user_ref(db):
    """Documento raíz del dueño de este script dentro de Firestore (users/{email})."""
    return db.collection("users").document(OWNER_EMAIL)


def clean_title(title):
    title = re.sub(r"\s*\[[^\]]*\]\s*$", "", title or "").strip()
    title = re.sub(r"^\d{4}-\d{2}:\s*", "", title).strip()
    return title


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


def match_course(component, cleaned_title):
    # 1) título exacto conocido (viene de la página de Actividad de Blackboard)
    course = TITLE_MAP.get(cleaned_title.strip().lower())
    if course:
        return course
    # 2) código de asignatura en alguno de los campos (eventos "de cabecera")
    fields = ("SUMMARY", "DESCRIPTION", "CATEGORIES", "LOCATION", "UID")
    haystack = " ".join(str(component.get(f) or "") for f in fields)
    for code, name in COURSE_MAP.items():
        if code in haystack:
            return name
    return ""


def split_course_title(summary):
    """Último recurso si no se reconoce nada: separa por ':' o '-' como antes."""
    summary = clean_title(summary)
    for sep in (":", " - ", "–"):
        if sep in summary:
            course, _, title = summary.partition(sep)
            course, title = course.strip(), title.strip()
            if course and title:
                return course, title
    return "", summary


def event_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=MADRID)
        return value.astimezone(MADRID)
    if isinstance(value, date):
        return datetime.combine(value, dtime(23, 59), tzinfo=MADRID)
    return None


def dump_event_debug(n, component):
    print(f"--- DEBUG evento #{n}: TODOS los campos ---", file=sys.stderr)
    for key, value in component.items():
        print(f"  {key} = {value!r}", file=sys.stderr)
    print("--- fin DEBUG ---", file=sys.stderr)


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
    debug_dumped = 0

    for component in cal.walk("VEVENT"):
        uid = str(component.get("UID") or "")
        if not uid:
            continue

        if debug_dumped < DEBUG_EVENTS:
            debug_dumped += 1
            dump_event_debug(debug_dumped, component)

        doc_id = "bb-" + hashlib.md5(uid.encode("utf-8")).hexdigest()[:16]

        raw_summary = str(component.get("SUMMARY") or "(sin título)")
        cleaned_title = clean_title(raw_summary)
        course = match_course(component, cleaned_title)
        if course:
            title = cleaned_title
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