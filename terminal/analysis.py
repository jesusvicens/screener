"""Motor de análisis: réplica de tu Excel («Modelo EPS», «ROIC», «Escenarios», «Proy. *»).

Todo se calcula bajo demanda a partir de un objeto Financials. Las fórmulas siguen las de tu
hoja celda a celda; donde el Excel tenía errores (#REF! en el escenario Desastre y en el
control histórico del PER) aquí se calcula lo que la fórmula pretendía.
"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field, asdict

import pandas as pd

from .financials import Financials

PHASES = ["Crecimiento", "Madurez", "Estancamiento", "Declive", "Cíclica", "Recuperación"]
SCENARIOS = ["Optimista", "Base", "Adverso", "Desastre"]


def _div(a, b, default=None):
    try:
        if a is None or b is None or b == 0:
            return default
        return a / b
    except Exception:
        return default


def _sum(vals):
    v = [x for x in vals if x is not None]
    return sum(v) if v else None


def _cagr(last, first, n):
    if last is None or first is None or first <= 0 or last <= 0 or n <= 0:
        return None
    return (last / first) ** (1 / n) - 1


# ============================================================ Parámetros del inversor
@dataclass
class InvestorParams:
    price: float | None = None           # B5
    price_date: str = ""                 # B6
    r: float = 0.10                      # B7 rentabilidad exigida
    n: int = 10                          # B8 horizonte
    mos: float = 0.15                    # B9 margen de seguridad
    g_lt: float = 0.04                   # B10 crecimiento a largo plazo (PIB nominal)
    years_to_margin: int = 5             # B11
    rd_life: int = 5                     # ROIC!B30 vida útil del I+D capitalizado
    acciones_manual: float | None = None # acciones diluidas (M) si la SEC no da BPA (p. ej. varias clases de acciones)
    # Test de exposición (opcional)
    patrimonio: float | None = None
    importe: float | None = None
    deuda_posicion: float = 0.0


# ============================================================ Modelo EPS (histórico)
def eps_model(f: Financials, avg_prices: dict[int, float] | None = None) -> pd.DataFrame:
    avg_prices = avg_prices or {}
    rows = []
    prev = {}
    for y in f.years:
        price = avg_prices.get(y)
        eps = f.get("eps_diluted", y)
        sh = f.get("shares_diluted", y)
        divs = f.get("dividends", y)
        dps = _div(abs(divs), sh, 0.0) if divs is not None else 0.0
        rev, ni, eq = f.get("revenue", y), f.get("net_income", y), f.get("equity", y)
        bvps = _div(eq, sh)
        row = {
            "Año": y,
            "Precio medio": price,
            "Δ precio": _div((price - prev["price"]) if price and prev.get("price") else None, prev.get("price")),
            "BPA": eps,
            "Δ BPA": _div((eps - prev["eps"]) if eps is not None and prev.get("eps") else None, abs(prev["eps"]) if prev.get("eps") else None),
            "Rentabilidad (BPA/precio)": _div(eps, price),
            "PER": _div(price, eps) if (eps and eps > 0) else None,
            "Dividendo por acción": dps,
            "% dividendos s/ B": _div(dps, eps) if eps and eps > 0 else None,
            "Reservas por acción": (eps - dps) if eps is not None else None,
            "% reservas s/ B": _div(eps - dps, eps) if eps and eps > 0 else None,
            "Ventas (M)": rev,
            "Δ ventas": _div((rev - prev["rev"]) if rev is not None and prev.get("rev") else None, prev.get("rev")),
            "Beneficio (M)": ni,
            "Δ beneficio": _div((ni - prev["ni"]) if ni is not None and prev.get("ni") else None, abs(prev["ni"]) if prev.get("ni") else None),
            "Margen neto": _div(ni, rev),
            "Acciones (M)": sh,
            "Valor contable por acción": bvps,
            "Δ VC por acción": _div((bvps - prev["bvps"]) if bvps is not None and prev.get("bvps") else None, abs(prev["bvps"]) if prev.get("bvps") else None),
            "ROE": _div(ni, eq) if eq and eq > 0 else None,
        }
        rows.append(row)
        prev = {"price": price, "eps": eps, "rev": rev, "ni": ni, "bvps": bvps}
    return pd.DataFrame(rows).set_index("Año")


def per_history(eps_df: pd.DataFrame) -> dict:
    s = eps_df["PER"].dropna()
    s = s[s > 0]
    if s.empty:
        return {"PER medio": None, "PER sin outliers": None, "PER mínimo": None}
    trimmed = s.sort_values().iloc[1:-1] if len(s) >= 5 else s
    return {"PER medio": float(s.mean()), "PER sin outliers": float(trimmed.mean()), "PER mínimo": float(s.min())}


def buffettology(f: Financials, stats: dict, eps_df: pd.DataFrame, price: float | None, years: int = 10) -> dict:
    """Tu modelo original de Buffettología: el valor contable crece a ROE × % retenido."""
    y = f.years[-1]
    bvps = _div(f.get("equity", y), f.get("shares_diluted", y))
    roe = stats.get("roe5")
    ret = eps_df["% reservas s/ B"].dropna().tail(5).mean() if "% reservas s/ B" in eps_df else None
    per = per_history(eps_df)["PER sin outliers"]
    if bvps is None or bvps <= 0 or roe is None or ret is None or pd.isna(ret):
        return {}
    g = roe * ret
    bv_n = bvps * (1 + g) ** years
    eps_n = bv_n * roe
    out = {"VC por acción hoy": bvps, "ROE medio 5 años": roe, "% retenido medio 5 años": float(ret),
           "Crecimiento del VC (ROE × retenido)": g, f"VC por acción año {years}": bv_n, f"BPA año {years}": eps_n,
           "PER histórico sin outliers": per}
    if per:
        out[f"Precio año {years}"] = eps_n * per
        if price:
            out["Rentabilidad anual esperada"] = (eps_n * per / price) ** (1 / years) - 1
    return out


# ============================================================ ROIC
def roic(f: Financials, rd_life: int = 5) -> pd.DataFrame:
    ys = f.years
    d: dict[str, list] = {k: [] for k in [
        "Deuda a largo plazo", "Patrimonio neto", "(−) Caja e inversiones a corto", "Capital invertido (fin de año)",
        "Variación del capital invertido", "EBIT", "Tasa impositiva efectiva", "NOPAT", "Capital invertido medio",
        "ROIC", "Crecimiento del NOPAT ($)", "Crecimiento del NOPAT (%)", "ROIC incremental",
        "Gasto en I+D", "Amortización del I+D capitalizado", "Ajuste al EBIT", "EBIT ajustado", "NOPAT ajustado",
        "Activo de I+D capitalizado", "Capital invertido ajustado", "ROIC ajustado (I+D capitalizado)"]}
    ic_prev = nopat_prev = rd_asset_prev = icadj_prev = None
    rd_hist: list[float] = []
    for i, y in enumerate(ys):
        ltd = f.get("lt_debt", y, 0.0)
        eq = f.get("equity", y)
        cash = f.get("cash_sti", y, 0.0)
        ic = (ltd or 0) + (eq or 0) - (cash or 0) if eq is not None else None
        ebit = f.get("operating_income", y)
        tax = _div(f.get("taxes", y), f.get("pretax", y))
        nopat = ebit * (1 - tax) if (ebit is not None and tax is not None) else None
        ic_avg = ic if i == 0 or ic_prev is None else (ic + ic_prev) / 2 if ic is not None else None
        rd = f.get("rnd", y, 0.0) or 0.0
        rd_hist.append(rd)
        # Amortización: media móvil del I+D de los últimos `rd_life` años (como el OFFSET de tu hoja).
        window = rd_hist[-rd_life:]
        rd_amort = sum(window) / rd_life
        adj = rd - rd_amort
        ebit_adj = ebit + adj if ebit is not None else None
        nopat_adj = ebit_adj * (1 - tax) if (ebit_adj is not None and tax is not None) else None
        rd_asset = (rd - rd_amort) if rd_asset_prev is None else rd_asset_prev + rd - rd_amort
        icadj = ic + rd_asset if ic is not None else None
        icadj_avg = icadj if i == 0 or icadj_prev is None else (icadj + icadj_prev) / 2 if icadj is not None else None
        vals = [ltd, eq, -(cash or 0), ic, (ic - ic_prev) if (ic is not None and ic_prev is not None) else None, ebit, tax,
                nopat, ic_avg, _div(nopat, ic_avg) if ic_avg and ic_avg > 0 else None,
                (nopat - nopat_prev) if (nopat is not None and nopat_prev is not None) else None,
                (_div(nopat, nopat_prev) - 1) if (nopat is not None and nopat_prev) else None,
                _div((nopat - nopat_prev) if (nopat is not None and nopat_prev is not None) else None,
                     (ic - ic_prev) if (ic is not None and ic_prev is not None) else None),
                rd, rd_amort, adj, ebit_adj, nopat_adj, rd_asset, icadj,
                _div(nopat_adj, icadj_avg) if icadj_avg and icadj_avg > 0 else None]
        for k, v in zip(d.keys(), vals):
            d[k].append(v)
        ic_prev, nopat_prev, rd_asset_prev, icadj_prev = ic, nopat, rd_asset, icadj
    return pd.DataFrame(d, index=ys).T


# ============================================================ Histórico y fase (Escenarios §2)
def history_stats(f: Financials) -> dict:
    ys = f.years
    L = ys[-1]
    N = len(ys)
    last5 = ys[-5:]
    rev = {y: f.get("revenue", y) for y in ys}

    def back(k):
        return ys[-1 - k] if len(ys) > k else None

    def margin(num_key, y):
        return _div(f.get(num_key, y), rev.get(y))

    growth = [(_div(rev[ys[i]], rev[ys[i - 1]]) - 1) if rev.get(ys[i]) is not None and rev.get(ys[i - 1]) else None
              for i in range(1, N)]
    gm = [margin("gross_profit", y) for y in ys]
    om = [margin("operating_income", y) for y in ys]
    gm_v = [x for x in gm if x is not None]
    om_v = [x for x in om if x is not None]

    def ratio_sum(num, den, years):
        return _div(_sum(f.get(num, y) for y in years), _sum(f.get(den, y) for y in years))

    s: dict = {}
    s["rev_last_usd"] = (rev.get(L) or 0) * FX_USD.get((f.currency or "USD").upper(), 1.0)  # millones de $ (aprox.)
    s["g3"] = _cagr(rev.get(L), rev.get(back(3)), 3) if back(3) else None
    s["g5"] = _cagr(rev.get(L), rev.get(back(5)), 5) if back(5) else None
    s["g9"] = _cagr(rev.get(L), rev.get(ys[0]), N - 1) if N > 1 else None
    s["years_down"] = sum(1 for g in growth if g is not None and g < 0)
    s["gm_last"], s["gm5"], s["gm10"] = gm[-1], ratio_sum("gross_profit", "revenue", last5), ratio_sum("gross_profit", "revenue", ys)
    s["gm_min"], s["gm_max"] = (min(gm_v) if gm_v else None), (max(gm_v) if gm_v else None)
    s["om_last"], s["om5"], s["om10"] = om[-1], ratio_sum("operating_income", "revenue", last5), ratio_sum("operating_income", "revenue", ys)
    s["om_min"], s["om_max"] = (min(om_v) if om_v else None), (max(om_v) if om_v else None)
    roes = [_div(f.get("net_income", y), f.get("equity", y)) for y in last5]
    roes = [x for x in roes if x is not None]
    s["roe5"] = sum(roes) / len(roes) if roes else None
    s["share_chg5"] = _cagr(f.get("shares_diluted", L), f.get("shares_diluted", back(5)), 5) if back(5) else None
    fcf5 = _sum([(f.get("ocf", y) or 0) + (f.get("capex", y) or 0) for y in last5])
    eqnet5 = _sum(f.get("equity_net", y) for y in last5) or 0.0
    s["buyback_fcf5"] = min(max(_div(-eqnet5, fcf5, 0.0) or 0.0, 0.0), 1.2) if fcf5 else 0.0
    div5 = _sum(f.get("dividends", y) for y in last5) or 0.0
    s["payout5"] = (_div(max(-div5, 0.0), _sum(f.get("net_income", y) for y in last5), 0.0) or 0.0)
    s["payout5"] = max(s["payout5"], 0.0)
    s["tax5"] = min(max(ratio_sum("taxes", "pretax", last5) or 0.0, 0.0), 0.35)
    s["nonop_sales5"] = ratio_sum("nonop", "revenue", last5) or 0.0
    s["da_sales5"] = ratio_sum("da", "revenue", last5) or 0.0
    s["capex_sales5"] = -(ratio_sum("capex", "revenue", last5) or 0.0)
    s["sbc_sales5"] = ratio_sum("sbc", "revenue", last5) or 0.0
    s["rnd_opex5"] = ratio_sum("rnd", "opex", last5) or 0.0
    oca = sum((f.get(k, L) or 0) for k in ("receivables", "inventory", "prepaid", "other_current_assets"))
    s["oca"] = oca
    s["oca_sales"] = _div(oca, rev.get(L), 0.0)
    s["cl_sales"] = _div(f.get("current_liabilities", L), rev.get(L), 0.0)
    s["cyclical"] = bool(s["years_down"] >= 2 and s["om_max"] is not None and (s["om_max"] - s["om_min"]) >= 0.15)
    s["recovery"] = bool(s["om10"] is not None and s["om_last"] is not None and s["om10"] > 0.05 and s["om_last"] < 0.5 * s["om10"])
    g3 = s["g3"] if s["g3"] is not None else 0.0
    if s["recovery"]:
        phase = "Recuperación"
    elif s["cyclical"]:
        phase = "Cíclica"
    elif g3 >= 0.15:
        phase = "Crecimiento"
    elif g3 >= 0.05:
        phase = "Madurez"
    elif g3 >= -0.02:
        phase = "Estancamiento"
    else:
        phase = "Declive"
    s["phase"] = phase
    s["growth_series"] = dict(zip(ys[1:], growth))
    s["gm_series"] = dict(zip(ys, gm))
    s["om_series"] = dict(zip(ys, om))
    return s


STAT_LABELS = [
    ("g3", "Crecimiento anual de ventas, últimos 3 años (g3)", "pct"),
    ("g5", "Crecimiento anual de ventas, últimos 5 años", "pct"),
    ("g9", "Crecimiento anual de ventas, todo el periodo (g9)", "pct"),
    ("years_down", "Años con caída de ventas", "int"),
    ("gm_last", "Margen bruto del último año", "pct"), ("gm5", "Margen bruto medio 5 años", "pct"),
    ("gm10", "Margen bruto medio del periodo", "pct"), ("gm_min", "Margen bruto mínimo", "pct"), ("gm_max", "Margen bruto máximo", "pct"),
    ("om_last", "Margen operativo del último año", "pct"), ("om5", "Margen operativo medio 5 años", "pct"),
    ("om10", "Margen operativo medio del periodo", "pct"), ("om_min", "Margen operativo mínimo", "pct"),
    ("om_max", "Margen operativo máximo", "pct"),
    ("roe5", "ROE medio 5 años", "pct"), ("share_chg5", "Variación anual de acciones, 5 años (− = recompra neta)", "pct"),
    ("buyback_fcf5", "Recompras / flujo de caja libre, 5 años", "pct"), ("payout5", "Payout medio 5 años", "pct"),
    ("tax5", "Tipo impositivo medio 5 años", "pct"), ("nonop_sales5", "Resultado no operativo / ventas, 5 años", "pct"),
    ("da_sales5", "Amortizaciones / ventas, 5 años", "pct"), ("capex_sales5", "Capex / ventas, 5 años", "pct"),
    ("sbc_sales5", "Remuneración en acciones / ventas, 5 años", "pct"), ("rnd_opex5", "I+D / gastos operativos, 5 años", "pct"),
    ("oca_sales", "Activo circulante operativo / ventas (último año)", "pct"),
    ("cl_sales", "Pasivo circulante / ventas (último año)", "pct"),
    ("cyclical", "¿Señales de ciclicidad?", "bool"), ("recovery", "¿Señales de recuperación?", "bool"),
    ("phase", "Fase propuesta", "txt"),
]


# ============================================================ Escenarios (§3)
def exit_per(g10: float, r: float, roe5: float | None) -> float:
    g = min(g10, r - 0.03)
    roe = max(roe5 if roe5 is not None else 0.0, r + 0.01)
    return max(5.0, (1 - g / roe) * (1 + g) / (r - g))


# Tipos de cambio aproximados a $ (solo para saber el tamaño de la empresa al poner topes de crecimiento).
FX_USD = {"USD": 1.0, "EUR": 1.1, "GBP": 1.3, "CHF": 1.15, "SEK": 0.095, "DKK": 0.15, "NOK": 0.095, "PLN": 0.26,
          "CZK": 0.044, "HUF": 0.0028, "JPY": 0.0068, "CNY": 0.14, "HKD": 0.13, "CAD": 0.73, "AUD": 0.66, "ILS": 0.27,
          "TWD": 0.031, "KRW": 0.00073, "INR": 0.012, "BRL": 0.18, "MXN": 0.055, "ZAR": 0.055, "RON": 0.22, "ISK": 0.0073}


def tope_por_tamano(ventas_usd_m: float | None) -> float:
    """Crecimiento anual máximo de partida según el tamaño (ventas en millones de $): cuanto más grande, menos
    puede crecer durante años sin chocar con el tamaño de su mercado (una empresa de 200.000 M$ al 30 % anual
    facturaría 2,8 billones en diez años)."""
    v = ventas_usd_m or 0
    for lim, tope in ((1_000, 0.30), (10_000, 0.25), (50_000, 0.20), (150_000, 0.15)):
        if v < lim:
            return tope
    return 0.10


# Crecimiento máximo en el año 10 por escenario: a diez vista casi ninguna empresa sigue creciendo a doble dígito.
TOPE_G10 = {"Optimista": 0.12, "Base": 0.08, "Adverso": 0.05, "Desastre": 0.03}


def propose_scenarios(stats: dict, params: InvestorParams, phase: str) -> dict[str, dict]:
    i = PHASES.index(phase) if phase in PHASES else 1
    # Topes de cordura: ningún escenario propuesto parte de crecimientos de más del 30 % anual (ni menos del −30 %) ni de
    # márgenes imposibles (bruto entre 0 y 100 %; operativo entre −50 % y el bruto). Tus supuestos escritos a mano no se tocan.
    clip = lambda x, lo, hi: min(max(x, lo), hi)  # noqa: E731
    tope = tope_por_tamano(stats.get("rev_last_usd"))
    g3 = clip(stats.get("g3") or 0.0, -0.30, tope)
    g9 = clip(stats.get("g9") or 0.0, -0.30, tope)
    glt = params.g_lt
    gl, g5m, g10m, gmin, gmax = (clip(stats.get(k) or 0.0, 0.0, 1.0) for k in ("gm_last", "gm5", "gm10", "gm_min", "gm_max"))
    ol, o5, o10, omin, omax = (clip(stats.get(k) or 0.0, -0.5, 1.0) for k in ("om_last", "om5", "om10", "om_min", "om_max"))
    bb = stats.get("buyback_fcf5") or 0.0

    def pick(lst):
        return lst[i]

    sc = {
        "Optimista": {
            "g1": pick([g3, g3, max(g3, 0), 0, g9, g9]), "g10": pick([g3, g3, max(g3, 0), 0, g9, g9]),
            "gm": pick([gl, gl, gl, gl, gmax, g10m]), "om": pick([ol, ol, ol, ol, omax, o10]),
            "buyback": bb, "prob": pick([0.2, 0.2, 0.15, 0.1, 0.2, 0.25])},
        "Base": {
            "g1": pick([g3, g3, 0, g3, g9 / 2, g9 / 2]), "g10": pick([g3 / 2, glt, 0, g3 / 2, g9 / 2, g9 / 2]),
            "gm": pick([g5m, g5m, g5m, g5m, g10m, (gl + g10m) / 2]), "om": pick([o5, o5, o5, o5, o10, (ol + o10) / 2]),
            "buyback": bb, "prob": pick([0.45, 0.5, 0.5, 0.4, 0.4, 0.35])},
        "Adverso": {
            "g1": pick([g3 / 2, g3 / 2, -0.03, g3, 0, 0]), "g10": pick([0, 0, -0.03, g3, 0, 0]),
            "gm": pick([gmin, gmin, gmin, gmin, gmin, gl]), "om": pick([omin, omin, omin, omin, omin, ol]),
            "buyback": bb / 2, "prob": pick([0.25, 0.25, 0.25, 0.35, 0.3, 0.25])},
        "Desastre": {
            "g1": pick([0, -0.03, -0.08, 2 * g3, -0.05, -0.05]), "g10": pick([-0.05, -0.03, -0.08, 2 * g3, -0.05, -0.05]),
            "gm": pick([gmin - 0.05] * 5 + [gl - 0.05]),
            "om": pick([min(0.5 * omin, omin - 0.05)] * 5 + [min(0.5 * ol, ol - 0.05)]),
            "buyback": 0.0, "prob": pick([0.1, 0.05, 0.1, 0.15, 0.1, 0.15])},
    }
    for k in sc:
        sc[k]["g1"] = min(sc[k]["g1"], tope)
        sc[k]["g10"] = min(sc[k]["g10"], TOPE_G10.get(k, 0.12))
        sc[k]["gm"] = max(sc[k]["gm"], 0.0)
        sc[k]["om"] = min(sc[k]["om"], sc[k]["gm"])
        sc[k]["per_exit"] = exit_per(sc[k]["g10"], params.r, stats.get("roe5"))
    return sc


SCENARIO_FIELDS = [("g1", "Crecimiento de ventas en el año 1", "pct"), ("g10", "Crecimiento de ventas en el año 10", "pct"),
                   ("gm", "Margen bruto", "pct"), ("om", "Margen operativo", "pct"),
                   ("buyback", "Recompras (% del flujo de caja libre)", "pct"),
                   ("per_exit", "PER de salida (justificado por fundamentales)", "x"), ("prob", "Probabilidad", "pct")]


def merge_overrides(proposed: dict[str, dict], overrides: dict | None, params: InvestorParams, stats: dict) -> dict[str, dict]:
    """Aplica lo que tú hayas escrito encima. Si cambias g10 y no tocas el PER, el PER justificado se recalcula."""
    out = deepcopy(proposed)
    overrides = overrides or {}
    for scn, vals in overrides.items():
        if scn not in out:
            continue
        for k, v in (vals or {}).items():
            if v is not None and k in out[scn]:
                out[scn][k] = float(v)
        if "per_exit" not in (vals or {}) or vals.get("per_exit") is None:
            out[scn]["per_exit"] = exit_per(out[scn]["g10"], params.r, stats.get("roe5"))
    return out


# ============================================================ Proyección a 10 años («Proy. *»)
PROJ_ROWS = [
    "Crecimiento de ventas", "Ventas", "Coste de ventas", "Margen bruto", "Margen bruto %", "Gastos operativos",
    "   de los cuales I+D", "   comerciales, generales y otros", "Resultado operativo (EBIT)", "Margen operativo %",
    "Amortizaciones", "EBITDA", "Resultado no operativo", "Beneficio antes de impuestos", "Impuestos", "Beneficio neto",
    "Margen neto %", "Acciones diluidas (M)", "BPA diluido", "Crecimiento del BPA", "Dividendo por acción",
    "— FLUJO DE CAJA —", "Remuneración en acciones", "Variación del circulante", "Flujo de caja operativo", "Capex",
    "Flujo de caja libre", "PER supuesto para las recompras", "Precio supuesto para las recompras", "Recompra de acciones",
    "Dividendos pagados", "Variación de deuda", "Variación de caja",
    "— BALANCE —", "Caja e inversiones a corto", "Activo circulante operativo", "Activo no corriente", "Total activo",
    "Pasivo circulante", "Deuda a largo plazo", "Otros pasivos a largo plazo", "Patrimonio neto", "Total pasivo y patrimonio",
    "— RATIOS —", "ROE", "Valor contable por acción", "Deuda neta / EBITDA", "Flujo de caja libre por acción",
    "Variación de acciones en el año",
]


def project(f: Financials, stats: dict, sc: dict, params: InvestorParams) -> pd.DataFrame:
    L = f.years[-1]
    Y = max(1, params.years_to_margin)
    eps0 = f.get("eps_diluted", L) or 0.0
    per_paid = _div(params.price, eps0) if (params.price and eps0 > 0) else sc["per_exit"]

    c: dict[str, float | None] = {}
    c["Ventas"] = f.get("revenue", L) or 0.0
    c["Coste de ventas"] = f.get("cogs", L) or 0.0
    c["Margen bruto"] = f.get("gross_profit", L) or 0.0
    c["Margen bruto %"] = _div(c["Margen bruto"], c["Ventas"], 0.0)
    c["Crecimiento de ventas"] = (_div(f.get("revenue", L), f.get("revenue", f.years[-2])) - 1) if len(f.years) > 1 and f.get("revenue", f.years[-2]) else None
    c["Gastos operativos"] = f.get("opex", L)
    c["   de los cuales I+D"] = f.get("rnd", L)
    c["   comerciales, generales y otros"] = (c["Gastos operativos"] - (c["   de los cuales I+D"] or 0)) if c["Gastos operativos"] is not None else None
    c["Resultado operativo (EBIT)"] = f.get("operating_income", L) or 0.0
    c["Margen operativo %"] = _div(c["Resultado operativo (EBIT)"], c["Ventas"], 0.0)
    c["Amortizaciones"] = f.get("da", L) or 0.0
    c["EBITDA"] = c["Resultado operativo (EBIT)"] + c["Amortizaciones"]
    c["Resultado no operativo"] = f.get("nonop", L) or 0.0
    c["Beneficio antes de impuestos"] = f.get("pretax", L)
    c["Impuestos"] = f.get("taxes", L)
    c["Beneficio neto"] = f.get("net_income", L) or 0.0
    c["Margen neto %"] = _div(c["Beneficio neto"], c["Ventas"])
    c["Acciones diluidas (M)"] = f.get("shares_diluted", L) or 0.0
    c["BPA diluido"] = eps0
    c["Dividendo por acción"] = _div(abs(f.get("dividends", L) or 0.0), c["Acciones diluidas (M)"], 0.0)
    c["Remuneración en acciones"] = f.get("sbc", L)
    c["Flujo de caja operativo"] = f.get("ocf", L)
    c["Capex"] = f.get("capex", L)
    c["Flujo de caja libre"] = (c["Flujo de caja operativo"] or 0) + (c["Capex"] or 0)
    c["Recompra de acciones"] = f.get("equity_net", L)
    c["Dividendos pagados"] = -abs(f.get("dividends", L) or 0.0)
    c["Caja e inversiones a corto"] = f.get("cash_sti", L) or 0.0
    c["Activo circulante operativo"] = stats["oca"]
    c["Activo no corriente"] = f.get("lt_assets", L) or 0.0
    c["Total activo"] = c["Caja e inversiones a corto"] + c["Activo circulante operativo"] + c["Activo no corriente"]
    c["Pasivo circulante"] = f.get("current_liabilities", L) or 0.0
    c["Deuda a largo plazo"] = f.get("lt_debt", L) or 0.0
    c["Otros pasivos a largo plazo"] = (f.get("lt_liabilities", L) or 0.0) - c["Deuda a largo plazo"]
    c["Patrimonio neto"] = f.get("equity", L) or 0.0
    c["Total pasivo y patrimonio"] = c["Pasivo circulante"] + c["Deuda a largo plazo"] + c["Otros pasivos a largo plazo"] + c["Patrimonio neto"]
    c["ROE"] = _div(c["Beneficio neto"], c["Patrimonio neto"])
    c["Valor contable por acción"] = _div(c["Patrimonio neto"], c["Acciones diluidas (M)"])
    c["Deuda neta / EBITDA"] = _div(c["Deuda a largo plazo"] - c["Caja e inversiones a corto"], c["EBITDA"]) if c["EBITDA"] > 0 else None
    c["Flujo de caja libre por acción"] = _div(c["Flujo de caja libre"], c["Acciones diluidas (M)"])
    prev_sh = f.get("shares_diluted", f.years[-2]) if len(f.years) > 1 else None
    c["Variación de acciones en el año"] = (_div(c["Acciones diluidas (M)"], prev_sh) - 1) if prev_sh else None

    cols = {f"{L} real": c}
    p = c
    for t in range(1, 11):
        d: dict[str, float | None] = {}
        d["Crecimiento de ventas"] = sc["g1"] + (sc["g10"] - sc["g1"]) * (t - 1) / 9
        d["Ventas"] = p["Ventas"] * (1 + d["Crecimiento de ventas"])
        d["Margen bruto %"] = c["Margen bruto %"] + (sc["gm"] - c["Margen bruto %"]) * min(t / Y, 1)
        d["Coste de ventas"] = d["Ventas"] * (1 - d["Margen bruto %"])
        d["Margen bruto"] = d["Ventas"] - d["Coste de ventas"]
        d["Margen operativo %"] = c["Margen operativo %"] + (sc["om"] - c["Margen operativo %"]) * min(t / Y, 1)
        d["Resultado operativo (EBIT)"] = d["Ventas"] * d["Margen operativo %"]
        d["Gastos operativos"] = d["Margen bruto"] - d["Resultado operativo (EBIT)"]
        d["   de los cuales I+D"] = d["Gastos operativos"] * stats["rnd_opex5"]
        d["   comerciales, generales y otros"] = d["Gastos operativos"] - d["   de los cuales I+D"]
        d["Amortizaciones"] = d["Ventas"] * stats["da_sales5"]
        d["EBITDA"] = d["Resultado operativo (EBIT)"] + d["Amortizaciones"]
        d["Resultado no operativo"] = d["Ventas"] * stats["nonop_sales5"]
        d["Beneficio antes de impuestos"] = d["Resultado operativo (EBIT)"] + d["Resultado no operativo"]
        d["Impuestos"] = max(d["Beneficio antes de impuestos"], 0) * stats["tax5"]
        d["Beneficio neto"] = d["Beneficio antes de impuestos"] - d["Impuestos"]
        d["Margen neto %"] = _div(d["Beneficio neto"], d["Ventas"])
        # Flujo de caja
        d["Remuneración en acciones"] = d["Ventas"] * stats["sbc_sales5"]
        d["Activo circulante operativo"] = d["Ventas"] * stats["oca_sales"]
        d["Pasivo circulante"] = d["Ventas"] * stats["cl_sales"]
        d["Variación del circulante"] = -(d["Activo circulante operativo"] - p["Activo circulante operativo"]) + (d["Pasivo circulante"] - p["Pasivo circulante"])
        d["Flujo de caja operativo"] = d["Beneficio neto"] + d["Amortizaciones"] + d["Remuneración en acciones"] + d["Variación del circulante"]
        d["Capex"] = -d["Ventas"] * stats["capex_sales5"]
        d["Flujo de caja libre"] = d["Flujo de caja operativo"] + d["Capex"]
        d["PER supuesto para las recompras"] = per_paid + (sc["per_exit"] - per_paid) * (t - 1) / 9
        d["Precio supuesto para las recompras"] = max(p["BPA diluido"] or 0, 0) * d["PER supuesto para las recompras"]
        d["Recompra de acciones"] = -sc["buyback"] * max(d["Flujo de caja libre"] - d["Beneficio neto"] * stats["payout5"], 0)
        d["Dividendos pagados"] = -d["Beneficio neto"] * stats["payout5"] * (1 if d["Beneficio neto"] > 0 else 0)
        d["Variación de deuda"] = 0.0
        d["Variación de caja"] = d["Flujo de caja libre"] + d["Recompra de acciones"] + d["Dividendos pagados"] + d["Variación de deuda"]
        if d["Precio supuesto para las recompras"] > 0:
            d["Acciones diluidas (M)"] = p["Acciones diluidas (M)"] + (d["Remuneración en acciones"] + d["Recompra de acciones"]) / d["Precio supuesto para las recompras"]
            # tope: como mucho un 10 % menos de acciones al año (con un BPA casi nulo el precio supuesto tiende a cero y
            # las recompras comprarían la empresa entera)
            d["Acciones diluidas (M)"] = max(d["Acciones diluidas (M)"], 0.9 * p["Acciones diluidas (M)"])
        else:
            d["Acciones diluidas (M)"] = p["Acciones diluidas (M)"]
        d["BPA diluido"] = _div(d["Beneficio neto"], d["Acciones diluidas (M)"], 0.0)
        d["Crecimiento del BPA"] = (d["BPA diluido"] / p["BPA diluido"] - 1) if (p["BPA diluido"] or 0) > 0 else 0.0
        d["Dividendo por acción"] = max(d["BPA diluido"], 0) * stats["payout5"]
        # Balance
        d["Caja e inversiones a corto"] = p["Caja e inversiones a corto"] + d["Variación de caja"]
        d["Activo no corriente"] = p["Activo no corriente"] - d["Capex"] - d["Amortizaciones"]
        d["Total activo"] = d["Caja e inversiones a corto"] + d["Activo circulante operativo"] + d["Activo no corriente"]
        d["Deuda a largo plazo"] = p["Deuda a largo plazo"] + d["Variación de deuda"]
        d["Otros pasivos a largo plazo"] = p["Otros pasivos a largo plazo"]
        d["Patrimonio neto"] = p["Patrimonio neto"] + d["Beneficio neto"] + d["Remuneración en acciones"] + d["Recompra de acciones"] + d["Dividendos pagados"]
        d["Total pasivo y patrimonio"] = d["Pasivo circulante"] + d["Deuda a largo plazo"] + d["Otros pasivos a largo plazo"] + d["Patrimonio neto"]
        avg_eq = (p["Patrimonio neto"] + d["Patrimonio neto"]) / 2
        d["ROE"] = _div(d["Beneficio neto"], avg_eq, 0.0)
        d["Valor contable por acción"] = _div(d["Patrimonio neto"], d["Acciones diluidas (M)"])
        d["Deuda neta / EBITDA"] = _div(d["Deuda a largo plazo"] - d["Caja e inversiones a corto"], d["EBITDA"]) if d["EBITDA"] > 0 else None
        d["Flujo de caja libre por acción"] = _div(d["Flujo de caja libre"], d["Acciones diluidas (M)"])
        d["Variación de acciones en el año"] = _div(d["Acciones diluidas (M)"], p["Acciones diluidas (M)"], 1.0) - 1
        cols[str(L + t)] = d
        p = d
    df = pd.DataFrame({k: [v.get(r) for r in PROJ_ROWS] for k, v in cols.items()}, index=PROJ_ROWS)
    df.attrs["t"] = list(range(0, 11))
    return df


# ============================================================ Valoración (§4–§8)
@dataclass
class Valuation:
    by_scenario: pd.DataFrame
    coverage: dict
    value: dict
    window: pd.DataFrame
    exposure: pd.DataFrame | None
    projections: dict[str, pd.DataFrame]
    scenarios: dict[str, dict]
    warnings: list[str] = field(default_factory=list)


def valuation(f: Financials, stats: dict, scenarios: dict[str, dict], params: InvestorParams) -> Valuation:
    warnings = []
    P, r, n = params.price, params.r, max(1, min(10, int(params.n)))
    projs = {k: project(f, stats, v, params) for k, v in scenarios.items()}
    psum = sum(v["prob"] for v in scenarios.values())
    if abs(psum - 1) > 1e-4:
        warnings.append(f"Las probabilidades suman {psum:.0%}, no 100%.")
    rows = {}
    years = list(projs["Base"].columns[1:])

    def vf_parts(df, n_):
        col = years[n_ - 1]
        eps_n = df.at["BPA diluido", col]
        cash_ps = (df.at["Caja e inversiones a corto", col] - df.iloc[:, 0]["Caja e inversiones a corto"]) / df.at["Acciones diluidas (M)", col]
        dps = [df.at["Dividendo por acción", years[t - 1]] for t in range(1, n_ + 1)]
        div_cap = sum(d * (1 + r) ** (n_ - t) for t, d in enumerate(dps, start=1))
        return eps_n, cash_ps, div_cap

    U = P * (1 + r) ** n if P else None
    for k, sc in scenarios.items():
        eps_n, cash_ps, div_cap = vf_parts(projs[k], n)
        price_n = eps_n * sc["per_exit"]
        vf = price_n + cash_ps + div_cap
        ret = ((vf / P) ** (1 / n) - 1) if (P and vf > 0) else (-1.0 if P else None)
        rows[k] = {"BPA en el año n": eps_n, "PER de salida": sc["per_exit"], "Precio en el año n": price_n,
                   "Caja acumulada por acción": cash_ps, "Dividendos capitalizados a r": div_cap,
                   "Valor futuro (VF)": vf, "Rentabilidad anual": ret, "Probabilidad": sc["prob"],
                   "Exceso (+) / déficit (−) vs umbral": (vf - U) if U else None,
                   "Ponderado por probabilidad": (sc["prob"] * (vf - U)) if U else None}
    by = pd.DataFrame(rows)

    vfs = {k: rows[k]["Valor futuro (VF)"] for k in rows}
    pr = {k: scenarios[k]["prob"] for k in rows}
    EVF = sum(pr[k] * vfs[k] for k in rows)
    cov: dict = {"Umbral P·(1+r)^n": U, "Valor futuro esperado E[VF]": EVF}
    val: dict = {}
    if U:
        risk_p = sum(pr[k] for k in rows if vfs[k] < U)
        deficit = sum(pr[k] * (U - vfs[k]) for k in rows if vfs[k] < U)
        opp = sum(pr[k] * (vfs[k] - U) for k in rows if vfs[k] > U)
        cov.update({
            "Riesgo de no compensación (prob. de no llegar al umbral)": risk_p,
            "Riesgo asumido (déficit esperado)": deficit,
            "Déficit medio cuando no compensa": (deficit / risk_p) if risk_p > 0 else 0.0,
            "Oportunidad asumida (exceso esperado)": opp,
            "Valor asumido (oportunidad − riesgo)": opp - deficit,
            "Cobertura asumida (oportunidad / riesgo)": (opp / deficit) if deficit > 0 else "Sin cola izquierda",
            "Veredicto": "Compensa" if opp - deficit > 0 else "No compensa",
        })
        v_today = EVF / (1 + r) ** n
        max_p = v_today * (1 - params.mos)
        U2 = max_p * (1 + r) ** n
        d2 = sum(pr[k] * (U2 - vfs[k]) for k in rows if vfs[k] < U2)
        o2 = sum(pr[k] * (vfs[k] - U2) for k in rows if vfs[k] > U2)
        val = {
            "Valor estimado hoy = E[VF] / (1+r)^n": v_today,
            "Margen de seguridad al precio actual": 1 - P / v_today if v_today > 0 else None,
            "Rentabilidad anual implícita en la media": ((EVF / P) ** (1 / n) - 1) if EVF > 0 else -1.0,
            "Precio máximo de compra con tu margen": max_p,
            "Umbral al precio máximo": U2,
            "Cobertura al precio máximo": (o2 / d2) if d2 > 0 else "Sin cola izquierda",
            "Precio actual frente al precio máximo": (P / max_p - 1) if max_p > 0 else None,
        }

    # §7 Ventana de horizontes (escenario base)
    base = projs["Base"]
    eps0 = f.get("eps_diluted", f.years[-1]) or 0
    per_paid = _div(P, eps0) if (P and eps0 > 0) else None
    ref = scenarios["Base"]["per_exit"]
    wrows = {}
    for t in range(1, 11):
        B, C_, D = vf_parts(base, t)
        Ut = P * (1 + r) ** t if P else None
        req = ((Ut - D - C_) / B) if (Ut and B > 0) else None
        wrows[t] = {"BPA escenario base B(n)": B, "Umbral P·(1+r)^n": Ut, "Dividendos capitalizados D(n)": D,
                    "Caja acumulada por acción C(n)": C_, "Múltiplo de salida requerido": req, "Múltiplo de referencia": ref,
                    "¿Dentro de la ventana?": ("Sí" if (req is not None and req <= ref) else "No") if req is not None else "n.a.",
                    "Crecimiento del BPA que exige el precio": ((1 + r) * (per_paid / ref) ** (1 / t) - 1) if per_paid else None,
                    "Crecimiento del BPA en el escenario base": ((B / eps0) ** (1 / t) - 1) if (B > 0 and eps0 > 0) else -1.0}
    window = pd.DataFrame(wrows)

    # §8 Test de exposición
    expo = None
    if params.importe and P:
        e = {}
        for k in rows:
            res = vfs[k] / P - 1
            final = params.importe * vfs[k] / P
            own = final - (params.deuda_posicion or 0)
            effect = ((own - (params.importe - (params.deuda_posicion or 0))) / params.patrimonio) if params.patrimonio else None
            e[k] = {"Resultado del activo en el año n": res, "Valor final de la posición": final,
                    "Capital propio tras devolver la deuda": own, "Efecto sobre el patrimonio": effect}
        expo = pd.DataFrame(e)
    return Valuation(by_scenario=by, coverage=cov, value=val, window=window, exposure=expo, projections=projs,
                     scenarios=scenarios, warnings=warnings)


def params_from_dict(d: dict | None) -> InvestorParams:
    p = InvestorParams()
    for k, v in (d or {}).items():
        if hasattr(p, k) and v is not None:
            setattr(p, k, v)
    return p


def params_to_dict(p: InvestorParams) -> dict:
    return asdict(p)


def is_finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)
