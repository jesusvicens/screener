"""Resultados trimestrales de cualquier empresa a partir del XBRL de la SEC (10-Q y 10-K).

El cuarto trimestre no se publica por separado: se calcula como el año fiscal menos los tres primeros trimestres.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

REV_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax"]
TAGS = {"Ingresos": REV_TAGS, "Beneficio neto": ["NetIncomeLoss", "ProfitLoss"], "Resultado operativo": ["OperatingIncomeLoss"],
        "BPA GAAP": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]}


def _periods(facts: dict, tags: list[str]):
    g = (facts.get("facts") or {}).get("us-gaap") or {}
    q, fy = {}, {}
    for tag in tags:
        if tag not in g:
            continue
        for unit in g[tag]["units"].values():
            for x in unit:
                if x.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A") or "start" not in x:
                    continue
                d = (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days
                if 80 < d < 100:
                    q.setdefault(x["end"], (x["start"], x["val"]))
                elif 350 < d < 380:
                    fy.setdefault(x["end"], (x["start"], x["val"]))
    return q, fy


def quarterly(facts: dict, n_years: int = 5) -> pd.DataFrame:
    """Tabla trimestral (filas = fin de trimestre) con ingresos, beneficio, resultado operativo y BPA en millones / USD."""
    cols = {}
    for name, tags in TAGS.items():
        q, fy = _periods(facts, tags)
        s = {e: v for e, (_s, v) in q.items()}
        for end, (st_, tot) in fy.items():  # Q4 = año − 9 meses
            prev = [v for e, (s0, v) in q.items() if st_ <= s0 and e < end]
            if len(prev) == 3 and end not in s:
                s[end] = tot - sum(prev)
        cols[name] = s
    df = pd.DataFrame(cols).sort_index()
    if df.empty:
        return df
    for c in ("Ingresos", "Beneficio neto", "Resultado operativo"):
        if c in df:
            df[c] = df[c] / 1e6
    df.index = pd.to_datetime(df.index)
    df = df[df.index >= df.index.max() - pd.DateOffset(years=n_years)]
    if "Ingresos" in df:
        df["Crec. interanual ingresos"] = df["Ingresos"] / df["Ingresos"].shift(4) - 1
    return df
