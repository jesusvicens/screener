"""Dónde se guardan tus análisis (respuestas del examen, supuestos, notas, precio...).

- Sin configurar nada: en la carpeta data/analisis/ (sirve cuando la ejecutas en tu ordenador).
- Online (Streamlit Cloud): el disco del servidor se borra al reiniciar, así que se guardan como
  JSON en tu repositorio privado de GitHub. Basta con añadir en los «Secrets» de la app:
      GITHUB_TOKEN = "github_pat_..."     (token con permiso Contents: read/write sobre el repo)
      GITHUB_REPO  = "tuusuario/screener"
      GITHUB_BRANCH = "main"              (opcional)
  Cada guardado es un commit, así que tienes el historial de versiones de cada análisis.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path

import requests

LOCAL_DIR = Path(__file__).resolve().parent.parent / "data" / "analisis"
LOCAL_DIR.mkdir(parents=True, exist_ok=True)
REMOTE_DIR = "data/analisis"


def _secret(name: str) -> str | None:
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        return None


def backend() -> str:
    return "github" if (_secret("GITHUB_TOKEN") and _secret("GITHUB_REPO")) else "local"


def _gh(method: str, path: str, **kw):
    url = f"https://api.github.com/repos/{_secret('GITHUB_REPO')}/contents/{path}"
    headers = {"Authorization": f"Bearer {_secret('GITHUB_TOKEN')}", "Accept": "application/vnd.github+json"}
    return requests.request(method, url, headers=headers, timeout=30, **kw)


def _branch() -> str:
    return _secret("GITHUB_BRANCH") or "main"


def load(ticker: str) -> dict:
    t = ticker.upper()
    if backend() == "github":
        r = _gh("GET", f"{REMOTE_DIR}/{t}.json", params={"ref": _branch()})
        if r.status_code == 200:
            return json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
        return {}
    p = LOCAL_DIR / f"{t}.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def save(ticker: str, data: dict) -> str:
    t = ticker.upper()
    data = dict(data)
    data["ticker"] = t
    data["actualizado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if backend() == "github":
        path = f"{REMOTE_DIR}/{t}.json"
        cur = _gh("GET", path, params={"ref": _branch()})
        payload = {"message": f"Análisis {t} ({data['actualizado']})", "branch": _branch(),
                   "content": base64.b64encode(body.encode("utf-8")).decode("ascii")}
        if cur.status_code == 200:
            payload["sha"] = cur.json()["sha"]
        r = _gh("PUT", path, json=payload)
        r.raise_for_status()
        return f"Guardado en GitHub ({_secret('GITHUB_REPO')}/{path})"
    (LOCAL_DIR / f"{t}.json").write_text(body, "utf-8")
    return f"Guardado en {LOCAL_DIR / (t + '.json')}"


def list_all() -> list[dict]:
    out = []
    if backend() == "github":
        r = _gh("GET", REMOTE_DIR, params={"ref": _branch()})
        if r.status_code == 200:
            for it in r.json():
                if it["name"].endswith(".json") and not it["name"].startswith("_"):
                    out.append(load(it["name"][:-5]))
        return out
    for p in sorted(LOCAL_DIR.glob("[!_]*.json")):
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except Exception:
            pass
    return out


def delete(ticker: str) -> None:
    t = ticker.upper()
    if backend() == "github":
        path = f"{REMOTE_DIR}/{t}.json"
        cur = _gh("GET", path, params={"ref": _branch()})
        if cur.status_code == 200:
            _gh("DELETE", path, json={"message": f"Borra análisis {t}", "sha": cur.json()["sha"], "branch": _branch()})
        return
    p = LOCAL_DIR / f"{t}.json"
    if p.exists():
        p.unlink()
