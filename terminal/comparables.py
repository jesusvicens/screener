"""Comparables: empresas parecidas para poner a la tuya al lado (misma industria y tamaño parecido)."""
from __future__ import annotations

import math

import pandas as pd

COLS = ["Capitalización (M$)", "Ventas (M$)", "CAGR ventas 5a", "CAGR BPA 5a", "Margen bruto", "Margen operativo", "Margen FCF",
        "ROIC", "ROE medio 5a", "Deuda neta / EBITDA", "Var. acciones 5a", "PER", "P/FCF", "EV/EBIT", "Rent. FCF", "Nota financiera"]
# Para cada métrica, si más alto es mejor (True) o peor (False): sirve para la posición en el grupo.
HIGHER_IS_BETTER = {"CAGR ventas 5a": True, "CAGR BPA 5a": True, "Margen bruto": True, "Margen operativo": True, "Margen FCF": True,
                    "ROIC": True, "ROE medio 5a": True, "Deuda neta / EBITDA": False, "Var. acciones 5a": False, "PER": False,
                    "P/FCF": False, "EV/EBIT": False, "Rent. FCF": True, "Nota financiera": True}


def suggest(df: pd.DataFrame, ticker: str, n: int = 6, min_sales: float = 100) -> list[str]:
    """Hasta n empresas de la misma industria (si faltan, del mismo sector) con las ventas más parecidas."""
    u = df.drop_duplicates("CIK")
    me = df[df["Ticker"] == ticker]
    if me.empty:
        return []
    me = me.iloc[0]
    rev = me.get("Ventas (M$)") or 0
    pool = u[(u["Ticker"] != ticker) & (u["CIK"] != me["CIK"]) & (u["Ventas (M$)"].fillna(0) >= min_sales)]
    out: list[str] = []
    for col in ("Industria", "Sector"):
        val = me.get(col)
        if not val or val == "—":
            continue
        cand = pool[(pool[col] == val) & (~pool["Ticker"].isin(out))].copy()
        if rev and rev > 0:
            cand["_d"] = (cand["Ventas (M$)"].clip(lower=1).apply(math.log) - math.log(rev)).abs()
        else:
            cand["_d"] = -cand["Capitalización (M$)"].fillna(0)
        out += list(cand.sort_values("_d")["Ticker"].head(n - len(out)))
        if len(out) >= n:
            break
    return out


def table(df: pd.DataFrame, ticker: str, peers: list[str]) -> pd.DataFrame:
    """Filas = tu empresa, sus comparables y la mediana del grupo; columnas = métricas."""
    tick = [ticker] + [p for p in peers if p != ticker]
    sub = df[df["Ticker"].isin(tick)].drop_duplicates("Ticker").set_index("Ticker")
    sub = sub.reindex([t for t in tick if t in sub.index])
    cols = [c for c in COLS if c in sub.columns]
    out = sub[["Empresa"] + cols].copy()
    peers_only = out.drop(index=ticker, errors="ignore")
    if len(peers_only):
        med = peers_only[cols].apply(pd.to_numeric, errors="coerce").median()
        out.loc["Mediana"] = ["Mediana de los comparables"] + list(med.values)
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def position(tab: pd.DataFrame, ticker: str) -> dict[str, tuple[int, int]]:
    """Puesto de tu empresa en cada métrica (1 = la mejor) entre ella y sus comparables."""
    res = {}
    body = tab.drop(index="Mediana", errors="ignore")
    for c, hib in HIGHER_IS_BETTER.items():
        if c not in body or ticker not in body.index:
            continue
        s = pd.to_numeric(body[c], errors="coerce").dropna()
        if c in ("PER", "P/FCF", "EV/EBIT"):
            s = s[s > 0]
        if ticker not in s.index or len(s) < 2:
            continue
        rank = s.rank(ascending=not hib, method="min")
        res[c] = (int(rank[ticker]), len(s))
    return res
