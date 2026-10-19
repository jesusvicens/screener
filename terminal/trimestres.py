"""Resultados trimestrales de cualquier empresa a partir del XBRL de la SEC (10-Q y 10-K).

- El cuarto trimestre no se publica por separado: se calcula como el año fiscal menos los tres primeros trimestres.
- Los flujos de caja de los 10-Q son acumulados del año (3, 6 y 9 meses): cada trimestre es la diferencia.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

REV_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax"]
TAGS = {"Ingresos": REV_TAGS, "Beneficio bruto": ["GrossProfit"],
        "Resultado operativo": ["OperatingIncomeLoss"], "Beneficio neto": ["NetIncomeLoss", "ProfitLoss"],
        "BPA GAAP": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
        "Flujo de caja operativo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
        "Capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
        "Recompras": ["PaymentsForRepurchaseOfCommonStock"], "Dividendos": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
        "Acciones diluidas": ["WeightedAverageNumberOfDilutedSharesOutstanding"]}
MONEY = ("Ingresos", "Beneficio bruto", "Resultado operativo", "Beneficio neto", "Flujo de caja operativo", "Capex", "Recompras",
         "Dividendos", "Flujo de caja libre")


def _facts(facts: dict, tags: list[str]) -> dict[tuple[str, str], float]:
    """{(inicio, fin): valor} de 10-Q/10-K, la primera etiqueta con datos manda por periodo."""
    g = (facts.get("facts") or {}).get("us-gaap") or {}
    out: dict[tuple[str, str], float] = {}
    for tag in tags:
        if tag not in g:
            continue
        for unit in g[tag]["units"].values():
            for x in unit:
                if x.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A") or "start" not in x:
                    continue
                out.setdefault((x["start"], x["end"]), x["val"])
    return out


def _quarters(per: dict[tuple[str, str], float], additive: bool = True) -> dict[str, float]:
    days = lambda s, e: (date.fromisoformat(e) - date.fromisoformat(s)).days  # noqa: E731
    q = {e: v for (s, e), v in per.items() if 80 < days(s, e) < 100}
    if not additive:
        return q
    by_start: dict[str, list[tuple[str, float]]] = {}
    for (s, e), v in per.items():
        if 80 < days(s, e) < 380:
            by_start.setdefault(s, []).append((e, v))
    for s, lst in by_start.items():  # acumulados del año: 3 → 6 → 9 → 12 meses
        lst = sorted(set(lst))
        prev_e, prev_v = None, 0.0
        for e, v in lst:
            d = days(s, e)
            if prev_e is None:
                if 80 < d < 100:
                    prev_e, prev_v = e, v
                continue
            step = days(prev_e, e)
            if 80 < step < 100:
                q.setdefault(e, v - prev_v)
                prev_e, prev_v = e, v
    return q


def quarterly(facts: dict, n_years: int = 5) -> pd.DataFrame:
    """Tabla trimestral (filas = fin de trimestre) en millones (acciones en millones, BPA en $)."""
    cols = {}
    for name, tags in TAGS.items():
        cols[name] = _quarters(_facts(facts, tags), additive=name not in ("Acciones diluidas",))
    df = pd.DataFrame(cols).sort_index()
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated()]
    # quita trimestres «fantasma» (fechas a pocos días de otro trimestre por cambios de calendario)
    keep, last = [], None
    for d in df.index:
        if last is None or (d - last).days > 60:
            keep.append(d)
            last = d
    df = df.loc[keep]
    if "Flujo de caja operativo" in df:
        df["Flujo de caja libre"] = df["Flujo de caja operativo"] - df.get("Capex", 0).fillna(0)
    for c in MONEY:
        if c in df:
            df[c] = df[c] / 1e6
    if "Acciones diluidas" in df:  # el 4.º trimestre no trae acciones propias: se toma la media de sus vecinos
        df["Acciones diluidas"] = (df["Acciones diluidas"] / 1e6).interpolate(limit_area="inside").ffill()
    for c in ("Recompras", "Dividendos", "Capex"):
        if c in df:
            df[c] = df[c].abs()
    df = df[df.index >= df.index.max() - pd.DateOffset(years=n_years)]
    if "Ingresos" in df:
        df["Crec. interanual ingresos"] = df["Ingresos"] / df["Ingresos"].shift(4) - 1
    return df


def ttm(q: pd.DataFrame) -> pd.DataFrame:
    """Últimos 12 meses: suma de 4 trimestres (acciones: media)."""
    if q is None or q.empty:
        return q
    out = pd.DataFrame(index=q.index)
    for c in q.columns:
        if c.startswith("Crec."):
            continue
        out[c] = q[c].rolling(4, min_periods=4).mean() if c == "Acciones diluidas" else q[c].rolling(4, min_periods=4).sum()
    return out.dropna(how="all")
