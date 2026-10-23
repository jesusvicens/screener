"""Descripción del negocio de cada empresa (qué hace), para el screener, las listas y la ficha.

Fuente: el resumen de actividad de Yahoo Finance (en inglés) y, para las de EE. UU. que no lo tengan, el perfil de
Nasdaq. Lo prepara cada noche el proceso de datos (scripts/datos_screener.py → descripciones.json.gz en la rama
«datos») poco a poco: las que faltan primero y se renuevan cada seis meses. Si tienes dossier de la empresa, la
terminal usa antes tu «En una frase», que está en español.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests

FILE = "descripciones.json.gz"
_cache: dict = {"t": 0.0, "v": None}


# ---------------------------------------------------------------- lectura (app)
def todas() -> dict[str, dict]:
    """{ticker: {"en": texto, "fecha": "AAAA-MM-DD", "fuente": ...}} (caché de 12 h)."""
    if _cache["v"] is not None and time.time() - _cache["t"] < 12 * 3600:
        return _cache["v"]
    v: dict = {}
    try:
        from .sec import CACHE_DIR
        p = CACHE_DIR / FILE
        if p.exists() and time.time() - p.stat().st_mtime < 24 * 3600:
            v = json.loads(gzip.decompress(p.read_bytes()))
        else:
            from . import remoto
            raw = remoto.public_file(FILE, timeout=60)
            if raw:
                p.write_bytes(raw)
                v = json.loads(gzip.decompress(raw))
    except Exception:  # noqa: BLE001
        v = {}
    _cache.update(t=time.time(), v=v)
    return v


def larga(ticker: str) -> str:
    return ((todas().get((ticker or "").upper()) or {}).get("en") or "").strip()


def corta(ticker: str, max_chars: int = 240) -> str:
    """La primera frase (o dos, si la primera es muy corta), sin la forma jurídica repetida."""
    return resumir(larga(ticker), max_chars)


def resumir(txt: str, max_chars: int = 240) -> str:
    if not txt:
        return ""
    frases = re.split(r"(?<=[a-z0-9\)])\.\s+(?=[A-Z])", txt.strip())
    out = frases[0].rstrip(".") + "."
    if len(out) < 130 and len(frases) > 1:
        out += " " + frases[1].rstrip(".") + "."
    return out if len(out) <= max_chars else out[:max_chars - 1].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------- construcción (proceso nocturno)
def _yahoo(t: str) -> str | None:
    try:
        import yfinance as yf
        return (yf.Ticker(t if _eu(t) else t.replace(".", "-")).info or {}).get("longBusinessSummary")
    except Exception:  # noqa: BLE001
        return None


def _eu(t: str) -> bool:
    from .esef import is_european
    return is_european(t)


def _nasdaq(t: str) -> str | None:
    try:
        r = requests.get(f"https://api.nasdaq.com/api/company/{t}/company-profile",
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=20)
        return (((r.json() or {}).get("data") or {}).get("CompanyDescription") or {}).get("value")
    except Exception:  # noqa: BLE001
        return None


def actualizar(prev: dict, tickers: list[str], minutos: float = 15, renovar_dias: int = 180, hilos: int = 4) -> dict:
    """Completa las que faltan (por orden de importancia de la lista) y renueva las de más de `renovar_dias`."""
    hoy = date.today()
    out = dict(prev)

    def vieja(t):
        f = (out.get(t) or {}).get("fecha")
        try:
            return (hoy - date.fromisoformat(f)).days > renovar_dias
        except (TypeError, ValueError):
            return True

    pend = [t for t in tickers if t not in out] + [t for t in tickers if t in out and vieja(t)]
    fin = time.time() + minutos * 60

    def one(t):
        if time.time() > fin:
            return t, None
        txt, src = _yahoo(t), "Yahoo Finance"
        if not txt and not _eu(t):
            txt, src = _nasdaq(t), "Nasdaq"
        return t, ({"en": txt.strip(), "fecha": hoy.isoformat(), "fuente": src} if txt else None)

    n = 0
    with ThreadPoolExecutor(hilos) as ex:
        for t, r in ex.map(one, pend):
            if r:
                out[t] = r
                n += 1
    print(f"Descripciones: {n} nuevas o renovadas · {len(out):,} en total · pendientes {max(len(pend) - n, 0):,}")
    return out


def para(ticker: str, frases: dict | None = None, max_chars: int = 240) -> str:
    """Tu «En una frase» del dossier (en español) si la hay; si no, el resumen de la actividad."""
    f = ((frases or {}).get((ticker or "").upper()) or {}).get("frase") if frases else None
    return f or corta(ticker, max_chars)
