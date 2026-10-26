"""Tareas y recordatorios (documento «_TAREAS» del almacenamiento).

{"items": [{"id": "a1b2c3", "texto": "Revisar el criterio «Dirección»", "ticker": "ADBE", "fecha": "2026-12-10",
            "tipo": "revisión", "motivo": "primeros resultados con el nuevo CEO", "origen": "análisis",
            "hecha": false, "creada": "2026-10-26", "hecha_el": null}]}

Tipos: «revisión» (volver a mirar una empresa en una fecha o tras un hecho), «tarea» (algo que hacer) y
«recordatorio». Las añades tú desde Inicio o desde la ficha de una empresa, y también Claude cuando la conclusión de
un análisis dice «revisar en 12 meses / tras X».
"""
from __future__ import annotations

import uuid
from datetime import date

from . import storage

DOC = "_TAREAS"
TIPOS = {"revisión": "🔁", "tarea": "✅", "recordatorio": "🔔"}


def load() -> list[dict]:
    try:
        return list((storage.load(DOC) or {}).get("items") or [])
    except Exception:  # noqa: BLE001
        return []


def save(items: list[dict]):
    storage.save(DOC, {"items": items})


def nueva(texto: str, fecha: date | None = None, ticker: str | None = None, tipo: str = "tarea",
          motivo: str = "", origen: str = "manual") -> dict:
    return {"id": uuid.uuid4().hex[:8], "texto": texto.strip(), "ticker": (ticker or "").upper() or None,
            "fecha": fecha.isoformat() if fecha else None, "tipo": tipo if tipo in TIPOS else "tarea",
            "motivo": motivo.strip(), "origen": origen, "hecha": False, "creada": date.today().isoformat(), "hecha_el": None}


def add(item: dict) -> list[dict]:
    items = load() + [item]
    save(items)
    return items


def marcar(id_: str, hecha: bool = True) -> list[dict]:
    items = load()
    for x in items:
        if x.get("id") == id_:
            x["hecha"] = hecha
            x["hecha_el"] = date.today().isoformat() if hecha else None
    save(items)
    return items


def borrar(id_: str) -> list[dict]:
    items = [x for x in load() if x.get("id") != id_]
    save(items)
    return items


def pendientes(items: list[dict] | None = None, ticker: str | None = None) -> list[dict]:
    items = load() if items is None else items
    out = [x for x in items if not x.get("hecha") and (ticker is None or x.get("ticker") == ticker.upper())]
    return sorted(out, key=lambda x: (x.get("fecha") or "9999-12-31", x.get("creada") or ""))
