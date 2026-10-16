"""Acceso a la API gratuita de la SEC (EDGAR / XBRL).

- Universo: todas las empresas con ticker registradas en la SEC (~10.000).
- companyfacts: todos los datos contables XBRL de una empresa (10-K, 10-Q, 20-F...).
- frames: un dato concreto (p. ej. Revenues de 2024) para TODAS las empresas en una sola llamada.

La SEC pide identificarse con un User-Agent "Nombre email" y no superar 10 peticiones/segundo.
"""
from __future__ import annotations

import gzip
import json
import os
import threading
import time
from pathlib import Path

import requests

CACHE_DIR = Path(os.environ.get("TERMINAL_CACHE", Path(__file__).resolve().parent.parent / "data" / "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_UA = "Terminal personal de analisis contacto@example.com"

_lock = threading.Lock()
_last_call = [0.0]


def _user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        try:
            import streamlit as st  # noqa: WPS433
            ua = st.secrets.get("SEC_USER_AGENT")  # type: ignore[attr-defined]
        except Exception:
            ua = None
    return ua or DEFAULT_UA


def _get(url: str, timeout: int = 60) -> requests.Response:
    # Respeta el límite de la SEC (máx. 10 req/s): dejamos 0,12 s entre llamadas.
    with _lock:
        wait = 0.12 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
    r = requests.get(url, headers={"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
    r.raise_for_status()
    return r


def _cached_json(name: str, url: str, max_age_h: float) -> dict:
    path = CACHE_DIR / f"{name}.json.gz"
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_h * 3600:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    data = _get(url).json()
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return data


# ---------------------------------------------------------------- universo
def universe(max_age_h: float = 24) -> list[dict]:
    """Lista de empresas: cik, nombre, ticker, mercado."""
    raw = _cached_json("universe", "https://www.sec.gov/files/company_tickers_exchange.json", max_age_h)
    fields = raw["fields"]
    out = [dict(zip(fields, row)) for row in raw["data"]]
    for x in out:
        x["exchange"] = x.get("exchange") or "—"
    return out


def find(ticker: str) -> dict | None:
    t = ticker.strip().upper().replace(".", "-")
    for x in universe():
        if x["ticker"].upper() == t:
            return x
    return None


# ---------------------------------------------------------------- datos de una empresa
def company_facts(cik: int, max_age_h: float = 24) -> dict:
    return _cached_json(f"facts_{int(cik):010d}", f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", max_age_h)


def submissions(cik: int, max_age_h: float = 24) -> dict:
    """Metadatos y lista de presentaciones (10-K, 10-Q, 8-K...)."""
    return _cached_json(f"subs_{int(cik):010d}", f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", max_age_h)


def filings(cik: int, forms: tuple[str, ...] = ("10-K", "10-Q", "8-K", "20-F", "DEF 14A"), limit: int = 40) -> list[dict]:
    s = submissions(cik)
    r = s.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(r.get("form", [])):
        if form in forms:
            acc = r["accessionNumber"][i].replace("-", "")
            doc = r["primaryDocument"][i]
            out.append({
                "form": form,
                "fecha": r["filingDate"][i],
                "periodo": r.get("reportDate", [""] * (i + 1))[i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}",
            })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- frames (todas las empresas a la vez)
def frame(tag: str, period: str, unit: str = "USD", taxonomy: str = "us-gaap", max_age_h: float = 24 * 7) -> dict[int, float]:
    """Devuelve {cik: valor} para todas las empresas. period: 'CY2024' (anual) o 'CY2024Q4I' (saldo a cierre)."""
    try:
        raw = _cached_json(f"frame_{taxonomy}_{tag}_{unit.replace('/', '-')}_{period}",
                           f"https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json", max_age_h)
    except requests.HTTPError:
        return {}
    return {int(x["cik"]): float(x["val"]) for x in raw.get("data", [])}
