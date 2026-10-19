"""Compras y ventas de directivos y consejeros (formularios 4 de la SEC).

Lo relevante son las compras en mercado (código P): un directivo solo compra con su dinero si cree que la acción está barata.
Las ventas (S) son menos informativas (impuestos, diversificación, planes 10b5-1 programados).
"""
from __future__ import annotations

import gzip
import json
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pandas as pd

from . import sec

CODES = {"P": "Compra en mercado", "S": "Venta en mercado", "A": "Concesión (acciones de regalo)", "M": "Ejercicio de opciones",
         "F": "Retención para impuestos", "G": "Donación", "C": "Conversión", "D": "Devolución a la empresa", "J": "Otra"}


def _t(node, path):
    x = node.find(path)
    return x.text.strip() if x is not None and x.text else None


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse(xml: str, fecha_pres: str, url: str) -> list[dict]:
    root = ET.fromstring(xml)
    owners = root.findall("reportingOwner")
    name = ", ".join(filter(None, (_t(o, "reportingOwnerId/rptOwnerName") for o in owners))) or "—"
    rel = owners[0].find("reportingOwnerRelationship") if owners else None
    roles = []
    if rel is not None:
        if _t(rel, "officerTitle"):
            roles.append(_t(rel, "officerTitle"))
        elif _t(rel, "isOfficer") in ("1", "true"):
            roles.append("Directivo")
        if _t(rel, "isDirector") in ("1", "true"):
            roles.append("Consejero")
        if _t(rel, "isTenPercentOwner") in ("1", "true"):
            roles.append("Accionista >10 %")
    plan = _t(root, "aff10b5One") in ("1", "true")
    out = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _t(tx, "transactionCoding/transactionCode")
        sh = _num(_t(tx, "transactionAmounts/transactionShares/value"))
        px = _num(_t(tx, "transactionAmounts/transactionPricePerShare/value"))
        ad = _t(tx, "transactionAmounts/transactionAcquiredDisposedCode/value")
        after = _num(_t(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"))
        out.append({"Fecha": _t(tx, "transactionDate/value"), "Presentado": fecha_pres, "Quién": name.title(), "Cargo": " · ".join(roles),
                    "Código": code, "Operación": CODES.get(code, code or "—"), "Acciones": (sh or 0) * (1 if ad == "A" else -1),
                    "Precio": px, "Importe": (sh or 0) * (px or 0) * (1 if ad == "A" else -1), "Tras la operación": after,
                    "Plan 10b5-1": plan, "url": url})
    return out


def transactions(cik: int, months: int = 24, max_filings: int = 80, max_age_h: float = 12) -> pd.DataFrame:
    """Operaciones de los formularios 4 de los últimos `months` meses (con caché en disco)."""
    path = sec.CACHE_DIR / f"insiders_{int(cik):010d}.json.gz"
    cache: dict = {}
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            cache = json.load(f)
        if time.time() - path.stat().st_mtime < max_age_h * 3600 and cache.get("_months") == months:
            return _df(cache)
    s = sec.submissions(int(cik), max_age_h=max_age_h)
    r = s.get("filings", {}).get("recent", {})
    since = (date.today() - timedelta(days=30 * months)).isoformat()
    todo = []
    for i, form in enumerate(r.get("form", [])):
        if form not in ("4", "4/A"):
            continue
        if r["filingDate"][i] < since or len(todo) >= max_filings:
            break
        acc = r["accessionNumber"][i]
        if acc not in cache:
            todo.append((acc, r["filingDate"][i], r["primaryDocument"][i]))

    def _one(item):
        acc, fdate, pdoc = item
        doc = pdoc.split("/")[-1]
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
        try:
            return acc, _parse(sec._get(base + doc).text, fdate, base + pdoc)
        except Exception:  # noqa: BLE001
            return acc, []

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:  # la SEC limita a 10 peticiones/s: _get ya espacia las llamadas
        for acc, rows in ex.map(_one, todo):
            cache[acc] = rows
    cache["_months"] = months
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(cache, f)
    return _df(cache)


def _df(cache: dict) -> pd.DataFrame:
    rows = [x for k, v in cache.items() if not k.startswith("_") for x in v]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    return df.sort_values("Fecha", ascending=False).reset_index(drop=True)


def summary(df: pd.DataFrame, months: int = 12) -> dict:
    if df is None or df.empty:
        return {}
    d = df[df["Fecha"] >= pd.Timestamp.today() - pd.DateOffset(months=months)]
    buys, sells = d[d["Código"] == "P"], d[d["Código"] == "S"]
    return {"compras": len(buys), "compradores": buys["Quién"].nunique(), "importe_compras": buys["Importe"].sum(),
            "ventas": len(sells), "vendedores": sells["Quién"].nunique(), "importe_ventas": -sells["Importe"].sum(),
            "ventas_plan": int(sells["Plan 10b5-1"].sum()) if "Plan 10b5-1" in sells else 0}
