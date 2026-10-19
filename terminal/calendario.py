"""Fechas de resultados: la última publicada (8-K con el punto 2.02 «Results of Operations») y la próxima estimada.

La SEC no publica fechas futuras: la próxima se estima con el patrón de la empresa (suele presentar
en la misma semana cada año). Es orientativa: confírmala en la web de relación con inversores.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import sec


def results_dates(cik: int, max_age_h: float = 24) -> list[date]:
    s = sec.submissions(int(cik), max_age_h=max_age_h)
    r = s.get("filings", {}).get("recent", {})
    items = r.get("items") or [""] * len(r.get("form", []))
    out = [date.fromisoformat(r["filingDate"][i]) for i, f in enumerate(r.get("form", []))
           if f == "8-K" and "2.02" in (items[i] or "")]
    if len(out) < 2:  # sin 8-K de resultados: usamos los 10-Q / 10-K
        out = [date.fromisoformat(r["filingDate"][i]) for i, f in enumerate(r.get("form", [])) if f in ("10-Q", "10-K")]
    # una fecha por trimestre (a veces hay 8-K/A o dos 8-K seguidos)
    out = sorted(set(out), reverse=True)
    dedup = []
    for d in out:
        if not dedup or (dedup[-1] - d).days > 40:
            dedup.append(d)
    return dedup


def next_results(cik: int) -> dict:
    ds = results_dates(cik)
    if not ds:
        return {}
    last = ds[0]
    today = date.today()
    nxt = None
    # misma época del año anterior: la presentación que siguió a la de hace ~1 año
    for d in ds:
        if 300 <= (last - d).days <= 420:
            later = [x for x in ds if d < x <= d + timedelta(days=130)]
            if later:
                nxt = min(later) + timedelta(days=364)
            break
    if nxt is None or nxt <= last:
        gaps = [(a - b).days for a, b in zip(ds, ds[1:5])]
        nxt = last + timedelta(days=int(sorted(gaps)[len(gaps) // 2]) if gaps else 91)
    while nxt < today - timedelta(days=3):  # si ya pasó y aún no hay 8-K, la próxima es la siguiente
        nxt += timedelta(days=91)
    return {"ultimo": last, "proximo": nxt, "dias": (nxt - today).days, "historial": ds[:8]}
