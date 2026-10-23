"""Proyección estándar (4 escenarios propuestos por fase) para TODO el universo del screener.

El proceso de datos calcula para cada empresa el valor futuro por acción de cada escenario (año n, con r = 10 % y
n = 10 años, los parámetros por defecto de la ficha) y su probabilidad. Con eso, la terminal recalcula al momento, con
el precio de hoy, lo mismo que la ficha: test de cobertura (oportunidad / riesgo frente al umbral P·(1+r)^n), valor
estimado (E[VF] / (1+r)^n), margen de seguridad y rentabilidad implícita.

El precio solo entra en la proyección por el precio al que se recompran acciones; por eso los valores futuros se
calculan con el precio del día del proceso y valen hasta el siguiente.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import analysis as A

ESC = ("Optimista", "Base", "Adverso", "Desastre")
R, N, MOS = 0.10, 10, 0.15
COLS = [f"_vf_{k}" for k in ESC] + [f"_p_{k}" for k in ESC] + ["_moneda"]
VF_COLS = [c for c in COLS if c != "_moneda"]
TOPE = 5.0  # valor estimado de más de 5 veces el precio: casi siempre datos que no cuadran (split reciente, ADR en otra divisa…)
OUT = ["Cobertura", "Margen de seguridad", "Valor estimado", "Rentab. implícita", "Prob. no compensar"]


def valores_futuros(fin, price: float | None = None, acciones: float | None = None) -> dict | None:
    """{_vf_Optimista: …, _p_Optimista: …, …} en la divisa del informe, o None si no se puede proyectar.

    `acciones` (millones): para las que no etiquetan BPA ni nº de acciones (p. ej. varias clases, como Visa), el BPA
    se calcula con las acciones actuales, igual que hace la ficha con «acciones a mano»."""
    try:
        L = fin.years[-1]
        eps = fin.get("eps_diluted", L)
        if eps is None and acciones and fin.get("net_income", L) is not None:
            import copy
            fin = copy.deepcopy(fin)
            for y in fin.years:
                ni = fin.get("net_income", y)
                if fin.get("eps_diluted", y) is None and ni is not None:
                    fin.data.setdefault("shares_diluted", {})[y] = acciones
                    fin.data.setdefault("eps_diluted", {})[y] = ni / acciones
            eps = fin.get("eps_diluted", L)
        if len(fin.years) < 4 or eps is None or not fin.get("revenue", L) or fin.get("operating_income", L) is None:
            return None  # sin resultado operativo (bancos y muchas aseguradoras) la proyección por márgenes no sirve
        stats = A.history_stats(fin)
        params = A.InvestorParams(price=price if price and price > 0 else None, r=R, n=N, mos=MOS)
        sc = A.propose_scenarios(stats, params, stats["phase"])
        out = {}
        for k in ESC:
            df = A.project(fin, stats, sc[k], params)
            col = df.columns[N]
            eps_n = df.at["BPA diluido", col]
            cash_ps = (df.at["Caja e inversiones a corto", col] - df.iloc[:, 0]["Caja e inversiones a corto"]) / df.at["Acciones diluidas (M)", col]
            div_cap = sum(df.at["Dividendo por acción", df.columns[t]] * (1 + R) ** (N - t) for t in range(1, N + 1))
            vf = eps_n * sc[k]["per_exit"] + cash_ps + div_cap
            if vf is None or not math.isfinite(vf):
                return None
            out[f"_vf_{k}"] = round(float(vf), 4)
            out[f"_p_{k}"] = round(float(sc[k]["prob"]), 4)
        return out
    except Exception:  # noqa: BLE001
        return None


def con_cobertura(df: pd.DataFrame) -> pd.DataFrame:
    """Añade Cobertura, Margen de seguridad, Valor estimado (divisa de cotización), Rentab. implícita y Prob. no compensar."""
    if not all(c in df for c in VF_COLS) or "Precio" not in df:
        for c in OUT:
            if c not in df:
                df[c] = np.nan
        return df
    fxq = pd.to_numeric(df.get("_fx_q"), errors="coerce") if "_fx_q" in df else pd.Series(np.nan, index=df.index)
    fxr = pd.to_numeric(df.get("_fx_r"), errors="coerce") if "_fx_r" in df else pd.Series(np.nan, index=df.index)
    conv = (fxq / fxr).where(fxq.notna() & fxr.notna() & (fxr > 0), 1.0)  # precio de cotización → divisa del informe
    P = pd.to_numeric(df["Precio"], errors="coerce").where(lambda s: s > 0) * conv
    vf = np.column_stack([pd.to_numeric(df[f"_vf_{k}"], errors="coerce") for k in ESC])
    pr = np.column_stack([pd.to_numeric(df[f"_p_{k}"], errors="coerce") for k in ESC])
    U = (P * (1 + R) ** N).to_numpy()[:, None]
    gap = vf - U
    deficit = np.nansum(np.where(gap < 0, -gap * pr, 0.0), axis=1)
    opp = np.nansum(np.where(gap > 0, gap * pr, 0.0), axis=1)
    risk = np.nansum(np.where(gap < 0, pr, 0.0), axis=1)
    evf = np.nansum(vf * pr, axis=1)
    ok = np.isfinite(vf).all(axis=1) & np.isfinite(U[:, 0])
    # Cuentas en otra divisa sin tipo de cambio (ADR que presentan en yuanes, etc.): no se puede comparar con el precio.
    if "_moneda" in df:
        mon = df["_moneda"].astype("string")
        ok &= ~(mon.notna() & (mon != "USD") & fxr.isna()).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ok &= ~((evf / (1 + R) ** N) > TOPE * P.to_numpy())
    df["Valoración dudosa"] = np.isfinite(vf).all(axis=1) & ~ok
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = np.where(deficit > 0, opp / deficit, np.inf)
        v_hoy = evf / (1 + R) ** N
        mos = np.where(v_hoy > 0, 1 - P.to_numpy() / v_hoy, np.nan)
        rent = np.where(evf > 0, (evf / P.to_numpy()) ** (1 / N) - 1, -1.0)
    df["Cobertura"] = np.where(ok, cov, np.nan)
    df["Margen de seguridad"] = np.where(ok, mos, np.nan)
    df["Valor estimado"] = np.where(ok | (np.isfinite(v_hoy) & ~np.isfinite(U[:, 0])), v_hoy / conv.to_numpy(), np.nan)
    df["Rentab. implícita"] = np.where(ok, rent, np.nan)
    df["Prob. no compensar"] = np.where(ok, risk, np.nan)
    return df
