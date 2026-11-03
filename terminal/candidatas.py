"""Análisis cualitativos que hace Claude cada día de las candidatas (empresas que aún no son tuyas).

Se guardan aparte de tus análisis (data/candidatas/ en tu repo de datos, no en data/analisis/), así una empresa
analizada por Claude no pasa a ser «tuya». «Recomendadas» usa su nota cualitativa para ordenar, y la ficha enseña su
dossier y propone sus respuestas del examen cualitativo hasta que guardes las tuyas.

Cada fichero <TICKER>.json: ticker, empresa, fecha, en_una_frase, examen {q02..q21: 1-3, 0 = no aplica}, motivos {qid: texto},
nota_cualitativa, dossier (Markdown con «### » por apartado), alertas [..], veredicto, fuentes [{titulo, url}].
_INDICE.json: {"empresas": {TICKER: {fecha, empresa, nota_cualitativa, en_una_frase, veredicto, alertas}}, "actualizado": …}.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from . import storage

REMOTE_DIR = "data/candidatas"
LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "candidatas"
INDICE = "_INDICE.json"


def _read(name: str) -> dict:
    if storage.backend() == "github":
        try:
            r = storage._gh("GET", f"{REMOTE_DIR}/{name}", params={"ref": storage._branch()})
        except Exception:  # noqa: BLE001
            return {}
        if r.status_code != 200:
            return {}
        js = r.json()
        if js.get("content"):
            return json.loads(base64.b64decode(js["content"]).decode("utf-8"))
        if js.get("download_url"):  # ficheros de más de 1 MB: la API no trae el contenido
            try:
                import requests
                rr = requests.get(js["download_url"], timeout=30,
                                  headers={"Authorization": f"Bearer {storage._secret('GITHUB_TOKEN')}"})
                return rr.json() if rr.status_code == 200 else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}
    p = LOCAL_DIR / name
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def indice() -> dict[str, dict]:
    """{TICKER: {fecha, empresa, nota_cualitativa, en_una_frase, veredicto, alertas}}"""
    return (_read(INDICE) or {}).get("empresas", {}) or {}


def load(ticker: str) -> dict:
    return _read(f"{ticker.upper()}.json")
