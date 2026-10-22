"""Conexión con tu OneDrive personal (Microsoft Graph): lee tus documentos y guarda el informe de la terminal.

Configuración (una vez):
1. Registra una aplicación en https://entra.microsoft.com (App registrations → New registration), con
   «Personal Microsoft accounts only», sin URI de redirección. Copia el «Application (client) ID».
2. En Authentication activa «Allow public client flows».
3. Pon el client id en DEFAULT_CLIENT_ID (abajo) o en los Secrets como ONEDRIVE_CLIENT_ID
4. En la ficha de una empresa → pestaña Seguimiento → «Documentos» → «Conectar OneDrive» y entra con tu cuenta.

Permisos que pide: Files.ReadWrite (leer tus ficheros y guardar el informe «… - Análisis terminal.docx» en la carpeta de
cada empresa; nunca modifica ni borra tus propios documentos), offline_access y User.Read.
Si conectaste antes con Files.Read (solo lectura), sigue funcionando para leer hasta que vuelvas a conectar.
El token de renovación se guarda en tu repo privado de datos (documento _ONEDRIVE).
"""
from __future__ import annotations

import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from . import storage

AUTH = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "Files.ReadWrite offline_access User.Read"
OLD_SCOPES = "Files.Read offline_access User.Read"
DOC = "_ONEDRIVE"
DEFAULT_ROOT = "Escritorio/AA. Jesús Vicens Noguer/INVERSIONS/00. SILVER LEGACY"

_tok: dict = {"access": None, "exp": 0.0}


class OneDriveError(Exception):
    pass


# Id. público de la aplicación «Terminal inversión» (cliente público, sin secreto: no da acceso a nada por sí solo;
# cada uno tiene que entrar con su propia cuenta). Se puede cambiar con ONEDRIVE_CLIENT_ID en los Secrets.
DEFAULT_CLIENT_ID = "fd79208b-08ce-458f-99be-26450ed16113"


def client_id() -> str | None:
    return storage._secret("ONEDRIVE_CLIENT_ID") or DEFAULT_CLIENT_ID


def configured() -> bool:
    return bool(client_id())


def _doc() -> dict:
    try:
        return storage.load(DOC) or {}
    except Exception:  # noqa: BLE001
        return {}


def settings() -> dict:
    d = _doc()
    return {"raiz": d.get("raiz") or DEFAULT_ROOT, "cuenta": d.get("cuenta"), "conectado": d.get("conectado"),
            "carpetas": d.get("carpetas") or {}}


def connected() -> bool:
    return bool(_doc().get("refresh_token"))


def can_write() -> bool:
    """True si al conectar diste permiso de escritura (para guardar el informe de la terminal)."""
    return "ReadWrite" in (_doc().get("permisos") or "")


def _save(**kw):
    d = _doc()
    d.update(kw)
    d.pop("ticker", None)
    d.pop("actualizado", None)
    storage.save(DOC, d)


def save_root(path: str):
    _save(raiz=path.strip().strip("/"))


def save_folder(ticker: str, path: str | None):
    d = _doc()
    c = dict(d.get("carpetas") or {})
    if path:
        c[ticker.upper()] = path
    else:
        c.pop(ticker.upper(), None)
    _save(carpetas=c)


def disconnect():
    d = _doc()
    for k in ("refresh_token", "cuenta", "conectado", "rt_guardado", "permisos"):
        d.pop(k, None)
    d.pop("ticker", None)
    d.pop("actualizado", None)
    storage.save(DOC, d)
    _tok.update(access=None, exp=0.0)


# ---------------------------------------------------------------- inicio de sesión (código de dispositivo)
def start_login() -> dict:
    """Devuelve {user_code, verification_uri, device_code, interval, expires_in, message}."""
    if not configured():
        raise OneDriveError("Falta ONEDRIVE_CLIENT_ID en los Secrets de la app.")
    r = requests.post(f"{AUTH}/devicecode", data={"client_id": client_id(), "scope": SCOPES}, timeout=30)
    j = r.json()
    if r.status_code != 200:
        raise OneDriveError(j.get("error_description") or j.get("error") or r.text)
    return j


def poll_login(device_code: str) -> str:
    """'pending' mientras esperas; 'ok' cuando has entrado (guarda el token); si no, el error."""
    r = requests.post(f"{AUTH}/token", timeout=30, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": client_id(), "device_code": device_code})
    j = r.json()
    if r.status_code == 200:
        _tok.update(access=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 120)
        name = None
        try:
            me = requests.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {j['access_token']}"}, timeout=20).json()
            name = me.get("userPrincipalName") or me.get("displayName")
        except Exception:  # noqa: BLE001
            pass
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _save(refresh_token=j["refresh_token"], cuenta=name, conectado=now, rt_guardado=now, permisos=SCOPES)
        return "ok"
    err = j.get("error", "")
    if err in ("authorization_pending", "slow_down"):
        return "pending"
    return j.get("error_description") or err or "error"


def _access_token() -> str:
    if _tok["access"] and time.time() < _tok["exp"]:
        return _tok["access"]
    d = _doc()
    rt = d.get("refresh_token")
    if not rt:
        raise OneDriveError("OneDrive no está conectado.")
    r = requests.post(f"{AUTH}/token", timeout=30, data={
        "grant_type": "refresh_token", "client_id": client_id(), "refresh_token": rt, "scope": d.get("permisos") or OLD_SCOPES})
    j = r.json()
    if r.status_code != 200:
        raise OneDriveError("La conexión con OneDrive ha caducado: vuelve a conectar. (" + (j.get("error") or "") + ")")
    _tok.update(access=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 120)
    # Microsoft renueva el token de refresco; lo guardamos como mucho una vez por semana para no llenar el repo de commits.
    new_rt = j.get("refresh_token")
    last = d.get("rt_guardado")
    try:
        old = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days if last else 99
    except ValueError:
        old = 99
    if new_rt and new_rt != rt and old >= 7:
        _save(refresh_token=new_rt, rt_guardado=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return _tok["access"]


def _get(url: str, **kw) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30, **kw)
    if r.status_code == 404:
        raise OneDriveError("No encuentro esa carpeta en tu OneDrive.")
    if r.status_code != 200:
        raise OneDriveError(f"OneDrive respondió {r.status_code}: {r.text[:200]}")
    return r.json()


# ---------------------------------------------------------------- ficheros
def _item(x: dict, parent: str) -> dict:
    return {"id": x["id"], "name": x["name"], "path": f"{parent}/{x['name']}".strip("/"), "folder": "folder" in x,
            "size": x.get("size"), "modified": (x.get("lastModifiedDateTime") or "")[:10], "url": x.get("webUrl"),
            "n_children": (x.get("folder") or {}).get("childCount")}


def children(path: str) -> list[dict]:
    path = path.strip("/")
    url = f"{GRAPH}/me/drive/root/children" if not path else f"{GRAPH}/me/drive/root:/{quote(path)}:/children"
    out, params = [], {"$top": 200, "$select": "id,name,size,lastModifiedDateTime,webUrl,folder,file"}
    while url:
        j = _get(url, params=params)
        out += [_item(x, path) for x in j.get("value", [])]
        url, params = j.get("@odata.nextLink"), None
    return sorted(out, key=lambda i: (not i["folder"], i["name"].lower()))


def tree(path: str, depth: int = 4) -> list[dict]:
    """Ficheros de la carpeta y sus subcarpetas (hasta `depth` niveles), con su ruta relativa."""
    out = []
    for it in children(path):
        if it["folder"]:
            if depth > 1:
                sub = tree(it["path"], depth - 1)
                out.append({**it, "children": sub})
            else:
                out.append({**it, "children": []})
        else:
            out.append(it)
    return out


def preview_url(item_id: str) -> str | None:
    """URL para incrustar la vista previa (PDF, Word, Excel, PowerPoint…)."""
    r = requests.post(f"{GRAPH}/me/drive/items/{item_id}/preview", headers={"Authorization": f"Bearer {_access_token()}"},
                      json={}, timeout=30)
    return r.json().get("getUrl") if r.status_code == 200 else None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    for w in (",", ".", " inc", " corp", " corporation", " holdings", " group", " ltd", " plc", " co", "&", "'"):
        s = s.replace(w, " ")
    return " ".join(s.split())


def candidate_folders(root: str) -> list[str]:
    """Carpetas de empresa: las de la raíz y las de sus subcarpetas «00 …» (p. ej. «00 Posicions obertes»)."""
    out = []
    for it in children(root):
        if not it["folder"]:
            continue
        if it["name"].startswith("00 ") or it["name"].lower().startswith("posicions"):
            out += [c["path"] for c in children(it["path"]) if c["folder"]]
        else:
            out.append(it["path"])
    return out


def guess_folder(folders: list[str], ticker: str, name: str) -> str | None:
    t = ticker.lower()
    n = _norm(name)
    first = n.split()[0] if n else ""
    for f in folders:
        leaf = _norm(f.rsplit("/", 1)[-1])
        if leaf == t or leaf == n or (first and (leaf == first or leaf.split()[0] == first)):
            return f
    return None


# ---------------------------------------------------------------- escribir (solo el informe de la terminal)
def item_info(path: str) -> dict | None:
    """Metadatos de un fichero (None si no existe)."""
    r = requests.get(f"{GRAPH}/me/drive/root:/{quote(path.strip('/'))}", headers={"Authorization": f"Bearer {_access_token()}"},
                     params={"$select": "id,name,lastModifiedDateTime,webUrl,size,description"}, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise OneDriveError(f"OneDrive respondió {r.status_code}: {r.text[:200]}")
    return r.json()


def set_description(item_id: str, text: str):
    requests.patch(f"{GRAPH}/me/drive/items/{item_id}", json={"description": text[:1000]}, timeout=30,
                   headers={"Authorization": f"Bearer {_access_token()}"})


def upload(folder: str, filename: str, content: bytes, mime: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document") -> dict:
    """Crea o sustituye folder/filename (solo se usa para el informe de la terminal, nunca para tus documentos)."""
    if not can_write():
        raise OneDriveError("La conexión con OneDrive es de solo lectura: vuelve a conectar para dar permiso de escritura.")
    path = f"{folder.strip('/')}/{filename}"
    r = requests.put(f"{GRAPH}/me/drive/root:/{quote(path)}:/content", data=content, timeout=120,
                     headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": mime})
    if r.status_code not in (200, 201):
        raise OneDriveError(f"No he podido guardar en OneDrive ({r.status_code}): {r.text[:200]}")
    return r.json()
