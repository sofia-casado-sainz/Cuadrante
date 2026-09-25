#!/usr/bin/env python3
"""
El "agente" de la Agenda. Cada mañana repasa las tareas activas de CADA
persona que use esta app (recorre toda la colección users/, así que sirve a
la vez para la cuenta de Canvas/UFV y la de Blackboard/UAH sin duplicar
nada) y le prepara, con IA (Gemini, gratis), una frase corta de "qué hacer
hoy" por cada tarea que tenga pendiente y no venza demasiado lejos.

Guarda esas frases en users/{email}/agenda/ (una por tarea, con id fijo
"auto-{id de la tarea}"), sin tocar nunca lo que la persona ya haya marcado
como hecho ni los apuntes propios que haya añadido a mano desde la app. Si
una tarea ya tiene su entrada en la Agenda, solo se le refresca el texto y
la fecha de vencimiento (por si cambió); si es la primera vez, se crea.

También manda un aviso push cuando algo de la Agenda (de una tarea o de un
apunte propio con fecha límite) vence mañana y sigue sin marcarse hecho.

Variables de entorno necesarias:
  GEMINI_API_KEY        clave gratuita de https://aistudio.google.com/apikey
  FIREBASE_CREDENTIALS  el JSON completo de la cuenta de servicio de Firebase (como texto)

Variables opcionales:
  VAPID_PRIVATE_KEY     para el aviso push del día antes (si no la pones, simplemente no avisa)
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import firebase_admin
from firebase_admin import credentials, firestore
from pywebpush import webpush, WebPushException

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
# RELLENA con la URL real de tu GitHub Pages, como en los otros scripts:
APP_URL = "https://TU-USUARIO.github.io/cuadrante/"

MADRID = ZoneInfo("Europe/Madrid")
HORIZONTE_DIAS = 21  # no metemos en la Agenda tareas que vencen dentro de más de 3 semanas


def fecha_de(due_at):
    """Convierte el due_at (ISO datetime) de una tarea a su fecha local de Madrid."""
    if not due_at:
        return None
    try:
        dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        return dt.astimezone(MADRID).date()
    except ValueError:
        return None


def pedir_planes_a_gemini(tareas):
    """tareas: lista de dicts con id/titulo/asignatura/dias_restantes.
    Devuelve un dict {id: texto}."""
    datos = [
        {"id": t["id"], "titulo": t["titulo"], "asignatura": t["asignatura"] or "sin asignatura",
         "dias_restantes": t["dias_restantes"]}
        for t in tareas
    ]
    prompt = f"""Eres el ayudante de agenda de una persona universitaria. Esta es su lista
de tareas activas, con los días que quedan hasta la entrega (un número
negativo significa que ya está vencida):

{json.dumps(datos, ensure_ascii=False, indent=2)}

Para cada tarea, escribe una frase MUY corta (máximo 18 palabras), en español
de España, en segunda persona, que le diga qué hacer HOY con esa tarea. No te
inventes contenido de la asignatura que no tengas (no sabes el temario ni el
enunciado): habla de organizarse, empezar, repartir el tiempo, avanzar,
revisar o entregar. Ajusta el tono a la urgencia: si quedan pocos días o ya
está vencida, transmite prioridad real; si quedan muchos, algo más tranquilo
(ir avanzando poco a poco, sin agobio).

Devuelve un array JSON con un objeto {{"id":..., "texto":...}} por cada tarea
de la lista, usando exactamente los mismos id que te he dado."""

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {"id": {"type": "STRING"}, "texto": {"type": "STRING"}},
                },
            },
            "temperature": 0.7,
        },
    }
    resp = requests.post(GEMINI_URL, params={"key": GEMINI_API_KEY}, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    try:
        texto_json = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Respuesta inesperada de Gemini: {json.dumps(data)[:500]}")
    return {item["id"]: item["texto"] for item in json.loads(texto_json) if item.get("id") and item.get("texto")}


def send_push(user_ref, title, body, url):
    if not VAPID_PRIVATE_KEY:
        return
    subs = list(user_ref.collection("pushSubscriptions").stream())
    if not subs:
        return
    payload = json.dumps({"title": title, "body": body, "url": url})
    for sdoc in subs:
        s = sdoc.to_dict() or {}
        sub_info = {"endpoint": s.get("endpoint"), "keys": s.get("keys", {})}
        try:
            webpush(
                subscription_info=sub_info, data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{user_ref.id}"},
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                sdoc.reference.delete()
            else:
                print(f"Aviso: no se pudo mandar push a {sdoc.id}: {e}", file=sys.stderr)


def procesa_usuario(user_doc, hoy):
    user_ref = user_doc.reference
    email = user_doc.id
    agenda_coll = user_ref.collection("agenda")

    # --- 1. Tareas activas (no hechas, con fecha, dentro del horizonte) ---
    tareas_activas = []
    for d in user_ref.collection("tasks").stream():
        t = d.to_dict() or {}
        if t.get("done"):
            continue
        fecha = fecha_de(t.get("due_at"))
        if not fecha:
            continue
        dias = (fecha - hoy).days
        if dias > HORIZONTE_DIAS:
            continue
        tareas_activas.append({
            "id": d.id, "titulo": t.get("title") or "(sin título)",
            "asignatura": t.get("course"), "dias_restantes": dias,
            "vencimiento": fecha.isoformat(),
        })

    if tareas_activas:
        try:
            planes = pedir_planes_a_gemini(tareas_activas)
        except (requests.HTTPError, RuntimeError) as e:
            print(f"[{email}] Error pidiendo planes a Gemini: {e}", file=sys.stderr)
            planes = {}

        creados, actualizados = 0, 0
        for t in tareas_activas:
            texto = planes.get(t["id"])
            if not texto:
                continue  # si Gemini no devolvió texto para esta, no tocamos su entrada
            ref = agenda_coll.document("auto-" + t["id"])
            if ref.get().exists:
                ref.set({"texto": texto, "vencimiento": t["vencimiento"]}, merge=True)
                actualizados += 1
            else:
                ref.set({
                    "texto": texto, "dia": hoy.isoformat(), "done": False,
                    "tipo": "tarea", "task_id": t["id"], "vencimiento": t["vencimiento"],
                    "fuente": "agente", "creado": datetime.now(timezone.utc).isoformat(),
                })
                creados += 1
        print(f"[{email}] {len(tareas_activas)} tareas activas: {creados} nuevas en la Agenda, {actualizados} actualizadas.")
    else:
        print(f"[{email}] Sin tareas activas para la Agenda.")

    # --- 2. Aviso: algo de la Agenda (tarea o apunte propio) vence mañana y sigue sin hacer ---
    manana = (hoy + timedelta(days=1)).isoformat()
    pendientes_manana = []
    for d in agenda_coll.stream():
        a = d.to_dict() or {}
        if a.get("done"):
            continue
        if a.get("vencimiento") == manana:
            pendientes_manana.append(a.get("texto", "(sin título)"))

    meta_ref = user_ref.collection("meta").document("sync")
    ya_avisado_hoy = (meta_ref.get().to_dict() or {}).get("agenda_notified_date") == hoy.isoformat()

    if pendientes_manana and not ya_avisado_hoy:
        body = ", ".join(pendientes_manana[:5])
        if len(pendientes_manana) > 5:
            body += f" y {len(pendientes_manana) - 5} más"
        send_push(user_ref, f"⏰ {len(pendientes_manana)} cosa(s) de tu Agenda vencen mañana", body, APP_URL)
        meta_ref.set({"agenda_notified_date": hoy.isoformat()}, merge=True)


def main():
    cred_json = os.environ["FIREBASE_CREDENTIALS"]
    cred = credentials.Certificate(json.loads(cred_json))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    hoy = datetime.now(MADRID).date()

    for user_doc in db.collection("users").stream():
        try:
            procesa_usuario(user_doc, hoy)
        except Exception as e:
            print(f"[{user_doc.id}] Error procesando su Agenda: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()