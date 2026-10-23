"""Agenda de Inicio: próximas fechas de resultados y noticias de las empresas que sigues.

Fechas, por orden de preferencia:
1. Confirmadas en el documento «_CALENDARIO» del almacenamiento (las escribe la tarea programada de noticias o tú):
   {"fechas": {"RMS.PA": {"fecha": "2027-02-13", "evento": "Resultados 2026", "hora": "antes de apertura",
                          "fuente": "https://…"}}}
2. Las que publica Yahoo Finance (calendario de resultados; vale para EE. UU. y Europa).
3. Estimadas con el patrón de la SEC (solo EE. UU.: misma semana que el año anterior).

Noticias: documento «_NOTICIAS» del almacenamiento, lo rellena cada día la tarea programada:
   {"items": [{"fecha": "2026-10-23", "ticker": "RMS.PA", "titular": "…", "resumen": "…", "fuente": "Reuters",
               "url": "https://…", "tipo": "resultados", "importancia": "alta"}], "actualizado": "2026-10-23 08:00"}
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from . import storage

TIPOS = {"resultados": "📊", "guías": "🎯", "directivos": "👤", "dividendos y recompras": "💶", "producto": "🧪",
         "adquisiciones": "🤝", "regulación": "⚖️", "sector": "🌐", "mercado": "📈", "otro": "📰"}
_yc: dict[str, tuple[float, dict]] = {}


def _d(x) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def confirmadas() -> dict:
    try:
        return (storage.load("_CALENDARIO") or {}).get("fechas", {}) or {}
    except Exception:  # noqa: BLE001
        return {}


def _yahoo(t: str) -> dict:
    """Próxima fecha de resultados según Yahoo (caché de 12 h)."""
    hit = _yc.get(t)
    if hit and time.time() - hit[0] < 12 * 3600:
        return hit[1]
    out: dict = {}
    try:
        import yfinance as yf
        cal = yf.Ticker(t).calendar or {}
        ds = cal.get("Earnings Date") if isinstance(cal, dict) else None
        ds = [x for x in (_d(v) for v in (ds or [])) if x]
        if ds:
            out = {"fecha": min(ds), "rango": max(ds) if max(ds) != min(ds) else None}
    except Exception:  # noqa: BLE001
        out = {}
    _yc[t] = (time.time(), out)
    return out


def _sec(cik) -> dict:
    try:
        if not cik or int(cik) <= 0:
            return {}
        from . import calendario
        nx = calendario.next_results(int(cik))
        return {"fecha": nx["proximo"], "ultimo": nx["ultimo"]} if nx else {}
    except Exception:  # noqa: BLE001
        return {}


def proximas(tickers: dict[str, int | None], dias: int = 120) -> list[dict]:
    """[{ticker, fecha, origen, evento, hora, fuente, dias}] de las próximas `dias` jornadas, ordenadas por fecha.

    `tickers` = {ticker: cik (0/None para las europeas)}."""
    hoy = date.today()
    conf = confirmadas()

    def one(item):
        t, cik = item
        c = conf.get(t) or {}
        f = _d(c.get("fecha"))
        if f and f >= hoy:
            return {"ticker": t, "fecha": f, "origen": "confirmada", "evento": c.get("evento") or "Resultados",
                    "hora": c.get("hora"), "fuente": c.get("fuente")}
        y = _yahoo(t)
        if y.get("fecha") and y["fecha"] >= hoy:
            return {"ticker": t, "fecha": y["fecha"], "origen": "Yahoo Finance", "evento": "Resultados",
                    "hasta": y.get("rango")}
        s = _sec(cik)
        if s.get("fecha") and s["fecha"] >= hoy:
            return {"ticker": t, "fecha": s["fecha"], "origen": "estimada", "evento": "Resultados (estimada)"}
        return None

    with ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(one, tickers.items()) if r]
    for r in res:
        r["dias"] = (r["fecha"] - hoy).days
    return sorted((r for r in res if r["dias"] <= dias), key=lambda r: (r["fecha"], r["ticker"]))


def noticias() -> dict:
    try:
        return storage.load("_NOTICIAS") or {}
    except Exception:  # noqa: BLE001
        return {}
