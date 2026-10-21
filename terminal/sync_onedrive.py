"""Mantiene en OneDrive, en la carpeta de cada empresa, el informe Word con lo que hay en la terminal.

- Se lanza al guardar cualquier cosa de una empresa (análisis, dossier, bitácora, comparables…) y al abrir su ficha
  (por si el análisis se actualizó desde fuera de la app, p. ej. cuando lo actualiza Claude).
- Solo sube si el informe de OneDrive es más antiguo que el último guardado de la app.
- Solo escribe su propio fichero («… - Análisis terminal.docx»): nunca toca tus documentos.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime

from . import onedrive as OD
from . import storage

_lock = threading.Lock()
_last: dict[str, dict] = {}  # ticker -> último resultado (para mostrarlo en la app)


def status(ticker: str) -> dict:
    return _last.get(ticker.upper(), {})


def _folder(T: str) -> str | None:
    return (OD.settings().get("carpetas") or {}).get(T)


def _hash(data: dict) -> str:
    """Huella del contenido (sin la fecha): si no cambia, no hace falta volver a subir el informe."""
    d = {k: v for k, v in data.items() if k not in ("actualizado", "ticker")}
    return "terminal:" + hashlib.sha1(json.dumps(d, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def sync(ticker: str, data: dict | None = None, force: bool = False) -> dict:
    """Sube el informe si hace falta. Devuelve {estado, mensaje, url?}."""
    T = ticker.upper()
    if T.startswith("_"):
        return {}
    with _lock:
        try:
            if not (OD.configured() and OD.connected()):
                res = {"estado": "sin_conexion", "mensaje": "OneDrive no está conectado."}
            elif not OD.can_write():
                res = {"estado": "solo_lectura", "mensaje": "La conexión con OneDrive es de solo lectura: reconecta para permitir guardar."}
            elif not (folder := _folder(T)):
                res = {"estado": "sin_carpeta", "mensaje": "Falta elegir la carpeta de OneDrive de esta empresa (pestaña Documentos)."}
            else:
                from . import informe
                data = data if data is not None else (storage.load(T) or {})
                name = (data.get("resumen") or {}).get("Empresa") or T
                fn = informe.filename(T, name)
                h = _hash(data)
                info = None if force else OD.item_info(f"{folder}/{fn}")
                if info and info.get("description") == h:
                    res = {"estado": "al_dia", "mensaje": f"Informe al día en OneDrive ({fn}).", "url": info.get("webUrl")}
                else:
                    up = OD.upload(folder, fn, informe.build(T, data, name))
                    try:
                        OD.set_description(up["id"], h)
                    except Exception:  # noqa: BLE001
                        pass
                    res = {"estado": "subido", "mensaje": f"Informe actualizado en OneDrive: {fn}.", "url": up.get("webUrl")}
        except Exception as e:  # noqa: BLE001
            res = {"estado": "error", "mensaje": f"No he podido actualizar el informe en OneDrive: {e}"}
        res["cuando"] = datetime.now().strftime("%H:%M")
        _last[T] = res
        return res


def sync_async(ticker: str, data: dict | None = None, force: bool = False):
    """Lo mismo en segundo plano (no bloquea la app)."""
    if ticker.upper().startswith("_"):
        return
    threading.Thread(target=sync, args=(ticker, data, force), daemon=True).start()
