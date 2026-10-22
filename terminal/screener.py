"""Screener de TODAS las cotizadas de EE. UU. (estilo macrotrends) con los «frames» de la SEC.

La SEC permite pedir un dato concreto (p. ej. las ventas de 2024) para todas las empresas en
una sola llamada. Con ~100 llamadas montamos una tabla de ~5.000 empresas con crecimientos a
1/3/5 años, márgenes, rentabilidad, salud financiera y política de capital. Con los precios
(descarga en lote) se añaden los ratios de valoración: PER, P/Ventas, P/VC, P/FCF, EV/EBIT...

Después filtras por cualquier métrica con mínimo y máximo.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

from . import prices, sec
from .financials import detect_split

CACHE = sec.CACHE_DIR
BASE_FILE = CACHE / "screener_base.pkl"
PRICES_FILE = CACHE / "screener_market.pkl"

REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"]

# ---------------------------------------------------------------- catálogo de métricas
# (columna, grupo, formato, explicación). formato: pct, x (múltiplo), m (millones), ps (por acción), int
METRICS: list[tuple[str, str, str, str]] = [
    ("Nota financiera", "Examen", "ps", "Nota del examen financiero (0-10): media de PyG, Balance, Cash Flow y Asignación de capital. Se recalcula cada semana"),
    ("Nota PyG", "Examen", "ps", "Bloque PyG del examen financiero (0-10)"),
    ("Nota Balance", "Examen", "ps", "Bloque Balance del examen financiero (0-10)"),
    ("Nota Cash Flow", "Examen", "ps", "Bloque Cash Flow del examen financiero (0-10)"),
    ("Nota Asignación de capital", "Examen", "ps", "Bloque Asignación de capital del examen financiero (0-10)"),
    ("Preguntas no aplicables", "Examen", "int", "Preguntas del examen en «No aplica» (de 21). Muchas = banco/aseguradora o pocos datos: nota menos fiable"),
    ("Capitalización (M$)", "Tamaño", "m", "Precio × acciones diluidas del último ejercicio"),
    ("Valor empresa (M$)", "Tamaño", "m", "Capitalización + deuda financiera − caja"),
    ("Ventas (M$)", "Tamaño", "m", "Ventas del último ejercicio"),
    ("Beneficio (M$)", "Tamaño", "m", "Beneficio neto del último ejercicio"),
    ("Crec. ventas 1a", "Crecimiento", "pct", "Ventas último año / año anterior − 1"),
    ("CAGR ventas 3a", "Crecimiento", "pct", "Crecimiento anual compuesto de las ventas, 3 años"),
    ("CAGR ventas 5a", "Crecimiento", "pct", "Crecimiento anual compuesto de las ventas, 5 años"),
    ("Crec. BPA 1a", "Crecimiento", "pct", "BPA diluido último año / año anterior − 1 (ajustado por splits)"),
    ("CAGR BPA 3a", "Crecimiento", "pct", "Crecimiento anual compuesto del BPA, 3 años"),
    ("CAGR BPA 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del BPA, 5 años"),
    ("Crec. medio ventas", "Crecimiento", "pct", "Media de los crecimientos anuales de las ventas en los últimos N años (eliges N junto al filtro, de 2 a 10)"),
    ("Crec. medio BPA", "Crecimiento", "pct", "Media de los crecimientos anuales del BPA en los últimos N años (eliges N junto al filtro, de 2 a 10). Exige BPA positivo como base cada año"),
    ("Crec. medio beneficio", "Crecimiento", "pct", "Media de los crecimientos anuales del beneficio neto en los últimos N años (N a elegir)"),
    ("Crec. medio FCF", "Crecimiento", "pct", "Media de los crecimientos anuales del flujo de caja libre en los últimos N años (N a elegir)"),
    ("CAGR beneficio 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del beneficio neto, 5 años"),
    ("CAGR flujo operativo 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del flujo de caja operativo, 5 años"),
    ("CAGR FCF 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del flujo de caja libre, 5 años"),
    ("CAGR patrimonio 5a", "Crecimiento", "pct", "Crecimiento anual compuesto del patrimonio neto, 5 años"),
    ("Años caída ventas", "Consistencia", "int", "Años (de 5) en que las ventas bajaron"),
    ("Años caída BPA", "Consistencia", "int", "Años (de 5) en que el BPA bajó"),
    ("Años con pérdidas", "Consistencia", "int", "Años (de 6) con beneficio neto negativo"),
    ("Margen bruto", "Márgenes", "pct", "Margen bruto / ventas"),
    ("Margen operativo", "Márgenes", "pct", "Resultado operativo / ventas"),
    ("Margen neto", "Márgenes", "pct", "Beneficio neto / ventas"),
    ("Margen FCF", "Márgenes", "pct", "(Flujo operativo − capex) / ventas"),
    ("I+D / ventas", "Márgenes", "pct", "Gasto en I+D / ventas"),
    ("SBC / ventas", "Márgenes", "pct", "Remuneración en acciones / ventas"),
    ("ROE", "Rentabilidad", "pct", "Beneficio neto / patrimonio"),
    ("ROE medio 5a", "Rentabilidad", "pct", "Media de los últimos 5 ROE"),
    ("ROA", "Rentabilidad", "pct", "Beneficio neto / activo total"),
    ("ROIC", "Rentabilidad", "pct", "EBIT × (1 − tipo efectivo) / (deuda + patrimonio − caja)"),
    ("Deuda / patrimonio", "Salud", "x", "Deuda financiera (corto + largo) / patrimonio"),
    ("Deuda neta / EBITDA", "Salud", "x", "(Deuda − caja) / (EBIT + amortizaciones)"),
    ("Liquidez corriente", "Salud", "x", "Activo corriente / pasivo corriente"),
    ("Años para repagar deuda con OCF", "Salud", "x", "Deuda financiera / flujo operativo"),
    ("Var. acciones 5a", "Capital", "pct", "Variación anual de las acciones diluidas (− = recompra neta)"),
    ("Payout", "Capital", "pct", "Dividendos / beneficio neto"),
    ("Recompras / FCF", "Capital", "pct", "Recompras brutas / flujo de caja libre"),
    ("FCF / beneficio", "Capital", "pct", "Flujo de caja libre / beneficio neto (calidad del beneficio)"),
    ("Capex / OCF", "Capital", "pct", "Capex / flujo operativo"),
    ("Precio", "Valoración", "ps", "Último cierre"),
    ("PER", "Valoración", "x", "Precio / BPA diluido del último ejercicio"),
    ("PEG", "Valoración", "x", "PER / (CAGR BPA 5a × 100)"),
    ("P/Ventas", "Valoración", "x", "Capitalización / ventas"),
    ("P/Valor contable", "Valoración", "x", "Capitalización / patrimonio"),
    ("P/FCF", "Valoración", "x", "Capitalización / flujo de caja libre"),
    ("EV/EBIT", "Valoración", "x", "Valor empresa / resultado operativo"),
    ("EV/EBITDA", "Valoración", "x", "Valor empresa / EBITDA"),
    ("Rent. beneficio", "Valoración", "pct", "BPA / precio (inversa del PER)"),
    ("Rent. FCF", "Valoración", "pct", "FCF / capitalización"),
    ("Rent. dividendo", "Valoración", "pct", "Dividendos pagados / capitalización"),
]
METRIC_KIND = {m: k for m, _g, k, _d in METRICS}
METRIC_HELP = {m: d for m, _g, _k, d in METRICS}
GROUPS = list(dict.fromkeys(g for _m, g, _k, _d in METRICS))
VALUATION = [m for m, g, _k, _d in METRICS if g == "Valoración" or m in ("Capitalización (M$)", "Valor empresa (M$)")]

# Filtros guardados de ejemplo: {métrica: (mín, máx)} en unidades «humanas» (porcentajes como 0.10 = 10 %).
PRESETS: dict[str, dict[str, tuple[float | None, float | None]]] = {
    "Mejores notas financieras": {"Nota financiera": (8.0, None), "Preguntas no aplicables": (None, 3), "Ventas (M$)": (300, None)},
    "Fisher / Munger: calidad que crece": {
        "Ventas (M$)": (500, None), "CAGR ventas 5a": (0.07, None), "CAGR BPA 5a": (0.08, None), "Años caída BPA": (None, 1),
        "ROE medio 5a": (0.15, None), "Margen operativo": (0.15, None), "FCF / beneficio": (0.8, None), "Deuda / patrimonio": (None, 1.0)},
    "Crecimiento de BPA fuerte": {"CAGR BPA 5a": (0.15, None), "CAGR BPA 3a": (0.15, None), "Años caída BPA": (None, 1), "Ventas (M$)": (300, None)},
    "Compounders baratos (PER ≤ 20)": {"CAGR BPA 5a": (0.10, None), "ROE medio 5a": (0.15, None), "Años caída ventas": (None, 1),
                                         "PER": (0, 20), "Ventas (M$)": (500, None)},
    "Máquinas de caja": {"Margen FCF": (0.20, None), "FCF / beneficio": (1.0, None), "Capex / OCF": (None, 0.25), "Ventas (M$)": (500, None)},
    "Recompradores": {"Var. acciones 5a": (None, -0.02), "Recompras / FCF": (0.5, None), "ROE": (0.15, None)},
    "Value clásico": {"PER": (0, 15), "P/Valor contable": (0, 2), "Deuda / patrimonio": (None, 0.8), "Años con pérdidas": (None, 0)},
}


def latest_year() -> int:
    """Último año natural con cobertura suficiente (los 10-K se presentan hasta 90 días después del cierre)."""
    y = date.today().year - 1
    if len(sec.frame("NetIncomeLoss", f"CY{y}")) < 4000:
        y -= 1
    return y


def _merged(tags: list[str], period: str, unit: str = "USD") -> dict[int, float]:
    out: dict[int, float] = {}
    for t in tags:
        for cik, v in sec.frame(t, period, unit).items():
            out.setdefault(cik, v)
    return out


def _cagr(a, b, n):
    return (a / b) ** (1 / n) - 1 if (a and b and a > 0 and b > 0 and n > 0) else None


def _d(a, b):
    return a / b if (a is not None and b not in (None, 0)) else None


def build_base(progress=None, years_back: int = 10) -> pd.DataFrame:
    """Fundamentales de todas las empresas (sin precios). ~1-2 min la primera vez; luego, caché semanal."""
    Y = latest_year()
    yrs = list(range(Y - years_back, Y + 1))
    hist_specs = {
        "rev": (REVENUE_TAGS, "", "USD"), "ni": (["NetIncomeLoss", "ProfitLoss"], "", "USD"),
        "eps": (["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"], "", "USD-per-shares"),
        "ocf": (["NetCashProvidedByUsedInOperatingActivities"], "", "USD"),
        "capex": (["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], "", "USD"),
        "sh": (["WeightedAverageNumberOfDilutedSharesOutstanding"], "", "shares"),
        "eq": (["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "Q4I", "USD"),
        "op": (["OperatingIncomeLoss"], "", "USD"),
    }
    last_specs = {
        "gp": (["GrossProfit"], ""), "assets": (["Assets"], "Q4I"), "ac": (["AssetsCurrent"], "Q4I"), "lc": (["LiabilitiesCurrent"], "Q4I"),
        "cash": (["CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalentsAtCarryingValue",
                  "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"], "Q4I"),
        "ltd": (["LongTermDebtNoncurrent", "LongTermDebt"], "Q4I"), "std": (["LongTermDebtCurrent", "DebtCurrent"], "Q4I"),
        "div": (["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"], ""), "bb": (["PaymentsForRepurchaseOfCommonStock"], ""),
        "da": (["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet",
                "DepreciationAmortizationAndOther", "Depreciation"], ""), "tax": (["IncomeTaxExpenseBenefit"], ""),
        "pretax": (["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], ""),
        "rnd": (["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                 "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost"], ""),
        "cogs": (["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"], ""), "sbc": (["ShareBasedCompensation"], ""),
    }
    steps = len(yrs) * len(hist_specs) + len(last_specs) + 1
    k = [0]

    def tick(msg):
        k[0] += 1
        if progress:
            progress(min(k[0] / steps, 1.0), msg)

    H: dict[str, dict[int, dict[int, float]]] = {m: {} for m in hist_specs}
    for y in yrs:
        for m, (tags, suf, unit) in hist_specs.items():
            tick(f"{m} {y}")
            H[m][y] = _merged(tags, f"CY{y}{suf}", unit)
    LT: dict[str, dict[int, float]] = {}
    for m, (tags, suf) in last_specs.items():
        tick(f"{m} {Y}")
        if suf == "Q4I":
            # Saldos: cierre de diciembre y, si la empresa cierra en otro mes, el trimestre más cercano.
            LT[m] = {}
            for q in ("Q4I", "Q3I", "Q2I"):
                for c, v in _merged(tags, f"CY{Y}{q}").items():
                    LT[m].setdefault(c, v)
        else:
            LT[m] = _merged(tags, f"CY{Y}{suf}")
    tick("universo")
    by_cik: dict[int, dict] = {}
    for u in sec.universe():
        by_cik.setdefault(int(u["cik"]), u)

    rows = []
    for cik, u in by_cik.items():
        g = {m: [H[m][y].get(cik) for y in yrs] for m in hist_specs}
        rev, ni, eps, sh, eq = g["rev"], g["ni"], g["eps"], g["sh"], g["eq"]
        if rev[-1] is None and ni[-1] is None:
            continue
        for i in range(1, len(yrs)):  # splits
            f = detect_split(sh[i] / sh[i - 1] if (sh[i] and sh[i - 1]) else None)
            if f:
                for j in range(i):
                    sh[j] = sh[j] * f if sh[j] else sh[j]
                    eps[j] = eps[j] / f if eps[j] is not None else None
        L = {m: LT[m].get(cik) for m in last_specs}
        fcf = [(o - (c or 0)) if o is not None else None for o, c in zip(g["ocf"], g["capex"])]
        R, NI, OP, EQ = rev[-1], ni[-1], g["op"][-1], eq[-1]
        debt = (L["ltd"] or 0) + (L["std"] or 0)
        cash = L["cash"] or 0
        ebitda = (OP + (L["da"] or 0)) if OP is not None else None
        tax_rate = min(max(_d(L["tax"], L["pretax"]) or 0.21, 0), 0.35) if L["pretax"] and L["pretax"] > 0 else 0.21
        ic = (debt + EQ - cash) if EQ is not None else None
        roes = [_d(n, e) for n, e in zip(ni[-5:], eq[-5:]) if e and e > 0 and n is not None]

        def downs(s):
            s = [x for x in s if x is not None]
            return sum(1 for a, b in zip(s, s[1:]) if b < a) if len(s) >= 3 else None

        rows.append({
            "Ticker": u["ticker"], "Empresa": u["name"], "Mercado": u["exchange"], "CIK": cik, "Año datos": Y,
            "_s_rev": rev, "_s_eps": eps, "_s_ni": ni, "_s_fcf": fcf,
            "BPA": eps[-1], "Acciones (M)": sh[-1] / 1e6 if sh[-1] else None,
            "_debt": debt, "_cash": cash, "_eq": EQ, "_fcf": fcf[-1], "_op": OP, "_ebitda": ebitda, "_div": L["div"], "_rev": R, "_ni": NI,
            "Ventas (M$)": R / 1e6 if R else None, "Beneficio (M$)": NI / 1e6 if NI is not None else None,
            "Crec. ventas 1a": (_d(R, rev[-2]) - 1) if (R and rev[-2]) else None,
            "CAGR ventas 3a": _cagr(R, rev[-4], 3), "CAGR ventas 5a": _cagr(R, rev[-6], 5),
            "Crec. BPA 1a": (_d(eps[-1], eps[-2]) - 1) if (eps[-1] is not None and eps[-2] and eps[-2] > 0) else None,
            "CAGR BPA 3a": _cagr(eps[-1], eps[-4], 3), "CAGR BPA 5a": _cagr(eps[-1], eps[-6], 5),
            "CAGR beneficio 5a": _cagr(NI, ni[-6], 5), "CAGR flujo operativo 5a": _cagr(g["ocf"][-1], g["ocf"][-6], 5),
            "CAGR FCF 5a": _cagr(fcf[-1], fcf[-6], 5), "CAGR patrimonio 5a": _cagr(EQ, eq[-6], 5),
            "Años caída ventas": downs(rev[-6:]), "Años caída BPA": downs(eps[-6:]),
            "Años con pérdidas": sum(1 for x in ni[-6:] if x is not None and x < 0) if any(x is not None for x in ni[-6:]) else None,
            "Margen bruto": _d(L["gp"], R) if L["gp"] is not None else (_d(R - L["cogs"], R) if (R and L["cogs"] is not None) else None), "Margen operativo": _d(OP, R), "Margen neto": _d(NI, R), "Margen FCF": _d(fcf[-1], R),
            "I+D / ventas": _d(L["rnd"], R), "SBC / ventas": _d(L["sbc"], R),
            "ROE": _d(NI, EQ) if EQ and EQ > 0 else None, "ROE medio 5a": sum(roes) / len(roes) if len(roes) >= 3 else None,
            "ROA": _d(NI, L["assets"]), "ROIC": _d(OP * (1 - tax_rate), ic) if (OP is not None and ic and ic > 0) else None,
            "Deuda / patrimonio": _d(debt, EQ) if EQ and EQ > 0 else None,
            "Deuda neta / EBITDA": _d(debt - cash, ebitda) if ebitda and ebitda > 0 else None,
            "Liquidez corriente": _d(L["ac"], L["lc"]),
            "Años para repagar deuda con OCF": _d(debt, g["ocf"][-1]) if g["ocf"][-1] and g["ocf"][-1] > 0 else None,
            "Var. acciones 5a": _cagr(sh[-1], sh[-6], 5),
            "Payout": _d(L["div"] or 0, NI) if NI and NI > 0 else None,
            "Recompras / FCF": _d(L["bb"] or 0, fcf[-1]) if fcf[-1] and fcf[-1] > 0 else None,
            "FCF / beneficio": _d(fcf[-1], NI) if NI and NI > 0 else None,
            "Capex / OCF": _d(g["capex"][-1] or 0, g["ocf"][-1]) if g["ocf"][-1] and g["ocf"][-1] > 0 else None,
        })
    return pd.DataFrame(rows)


def row_from_financials(fin, meta: dict, n: int = 11) -> dict | None:
    """Fila del screener a partir de unos estados ya construidos (lo usan las empresas europeas, ESEF).

    Mismas columnas que build_base; los importes en la divisa del informe (se pasan a $ al valorar).
    """
    if not fin.years:
        return None
    Y = fin.years[-1]
    yrs = list(range(Y - n + 1, Y + 1))
    M = 1e6

    def ser(k, mult=M):
        return [None if fin.get(k, y) is None else fin.get(k, y) * mult for y in yrs]

    rev, ni, eps, sh, eq = ser("revenue"), ser("net_income"), ser("eps_diluted", 1), ser("shares_diluted"), ser("equity")
    ocf, capex, op = ser("ocf"), ser("capex"), ser("operating_income")
    fcf = ser("fcf")
    if rev[-1] is None and ni[-1] is None:
        return None
    g = lambda k: None if fin.get(k, Y) is None else fin.get(k, Y) * M  # noqa: E731
    R, NI, OP, EQ = rev[-1], ni[-1], op[-1], eq[-1]
    debt = (g("lt_debt") or 0) + (g("st_debt") or 0)
    cash = g("cash_sti") or 0
    da = g("da")
    ebitda = (OP + (da or 0)) if OP is not None else None
    pretax, tax = g("pretax"), g("taxes")
    tax_rate = min(max(_d(tax, pretax) or 0.21, 0), 0.35) if pretax and pretax > 0 else 0.21
    ic = (debt + EQ - cash) if EQ is not None else None
    roes = [_d(a, e) for a, e in zip(ni[-5:], eq[-5:]) if e and e > 0 and a is not None]
    divs = -(g("dividends") or 0) or None
    bb = g("buybacks")
    capex_pos = -capex[-1] if capex[-1] is not None else None

    def downs(s):
        s = [x for x in s if x is not None]
        return sum(1 for a, b in zip(s, s[1:]) if b < a) if len(s) >= 3 else None

    gp = g("gross_profit")
    return {
        "Ticker": meta["ticker"], "Empresa": meta["name"], "Mercado": meta.get("exchange") or "Europa", "CIK": 0, "Año datos": Y,
        "Divisa": fin.currency, "LEI": meta.get("lei"),
        "_s_rev": rev, "_s_eps": eps, "_s_ni": ni, "_s_fcf": fcf,
        "BPA": eps[-1], "Acciones (M)": sh[-1] / M if sh[-1] else None,
        "_debt": debt, "_cash": cash, "_eq": EQ, "_fcf": fcf[-1], "_op": OP, "_ebitda": ebitda, "_div": divs, "_rev": R, "_ni": NI,
        "Ventas (M$)": R / M if R else None, "Beneficio (M$)": NI / M if NI is not None else None,
        "Crec. ventas 1a": (_d(R, rev[-2]) - 1) if (R and rev[-2]) else None,
        "CAGR ventas 3a": _cagr(R, rev[-4], 3), "CAGR ventas 5a": _cagr(R, rev[-6], 5),
        "Crec. BPA 1a": (_d(eps[-1], eps[-2]) - 1) if (eps[-1] is not None and eps[-2] and eps[-2] > 0) else None,
        "CAGR BPA 3a": _cagr(eps[-1], eps[-4], 3), "CAGR BPA 5a": _cagr(eps[-1], eps[-6], 5),
        "CAGR beneficio 5a": _cagr(NI, ni[-6], 5), "CAGR flujo operativo 5a": _cagr(ocf[-1], ocf[-6], 5),
        "CAGR FCF 5a": _cagr(fcf[-1], fcf[-6], 5), "CAGR patrimonio 5a": _cagr(EQ, eq[-6], 5),
        "Años caída ventas": downs(rev[-6:]), "Años caída BPA": downs(eps[-6:]),
        "Años con pérdidas": sum(1 for x in ni[-6:] if x is not None and x < 0) if any(x is not None for x in ni[-6:]) else None,
        "Margen bruto": _d(gp, R), "Margen operativo": _d(OP, R), "Margen neto": _d(NI, R), "Margen FCF": _d(fcf[-1], R),
        "I+D / ventas": _d(g("rnd"), R), "SBC / ventas": _d(g("sbc"), R),
        "ROE": _d(NI, EQ) if EQ and EQ > 0 else None, "ROE medio 5a": sum(roes) / len(roes) if len(roes) >= 3 else None,
        "ROA": _d(NI, g("total_assets")), "ROIC": _d(OP * (1 - tax_rate), ic) if (OP is not None and ic and ic > 0) else None,
        "Deuda / patrimonio": _d(debt, EQ) if EQ and EQ > 0 else None,
        "Deuda neta / EBITDA": _d(debt - cash, ebitda) if ebitda and ebitda > 0 else None,
        "Liquidez corriente": _d(g("current_assets"), g("current_liabilities")),
        "Años para repagar deuda con OCF": _d(debt, ocf[-1]) if ocf[-1] and ocf[-1] > 0 else None,
        "Var. acciones 5a": _cagr(sh[-1], sh[-6], 5),
        "Payout": _d(divs or 0, NI) if NI and NI > 0 else None,
        "Recompras / FCF": _d(bb or 0, fcf[-1]) if fcf[-1] and fcf[-1] > 0 else None,
        "FCF / beneficio": _d(fcf[-1], NI) if NI and NI > 0 else None,
        "Capex / OCF": _d(capex_pos or 0, ocf[-1]) if ocf[-1] and ocf[-1] > 0 else None,
    }


EU_BASE_FILE = CACHE / "europa_base.pkl"
EU_MARKET_FILE = CACHE / "europa_market.pkl"


def _load_eu(path) -> pd.DataFrame | None:
    try:
        return pd.read_pickle(path) if path.exists() else None
    except Exception:  # noqa: BLE001
        return None


def load_base(max_age_days: float = 7) -> pd.DataFrame | None:
    us = _load_us_base(max_age_days)
    eu = _load_eu(EU_BASE_FILE)
    if us is None or eu is None or eu.empty:
        return us
    return pd.concat([us, eu], ignore_index=True)


def _load_us_base(max_age_days: float = 7) -> pd.DataFrame | None:
    if BASE_FILE.exists() and (time.time() - BASE_FILE.stat().st_mtime) < max_age_days * 86400:
        df = pd.read_pickle(BASE_FILE)
        if "_s_eps" in df.columns:  # versiones antiguas sin series anuales: se reconstruye
            return df
    return None


# ---------------------------------------------------------------- crecimiento medio con N años a elegir
AVG_GROWTH = {"Crec. medio ventas": "_s_rev", "Crec. medio BPA": "_s_eps", "Crec. medio beneficio": "_s_ni", "Crec. medio FCF": "_s_fcf"}
AVG_YEARS = list(range(2, 11))
AVG_DEFAULT = 5


def avg_growth(series, n: int):
    """Media aritmética de los últimos n crecimientos anuales.

    El primer y el último año tienen que tener dato. Si falta algún año intermedio (la SEC no lo
    da para ese año natural), el tramo se reparte como crecimiento anual compuesto entre los dos
    datos que lo rodean. Si la base de un año es cero o negativa (pérdidas), no hay crecimiento
    que medir y la empresa queda fuera.
    """
    if series is None or len(series) < n + 1:
        return None
    s = [None if (x is None or pd.isna(x)) else float(x) for x in list(series)[-(n + 1):]]
    if s[0] is None or s[-1] is None:
        return None
    pts = [(i, x) for i, x in enumerate(s) if x is not None]
    g = []
    for (i, a), (j, b) in zip(pts, pts[1:]):
        k = j - i
        if a <= 0 or (k > 1 and b <= 0):
            return None
        g += [(b / a) ** (1 / k) - 1] * k
    return sum(g) / len(g)


def with_avg_growth(df: pd.DataFrame, years: dict[str, int] | None = None) -> pd.DataFrame:
    """Calcula las columnas «Crec. medio …» con los años elegidos para cada una (5 por defecto)."""
    years = years or {}
    df = df.copy()
    for m, col in AVG_GROWTH.items():
        n = int(years.get(m, AVG_DEFAULT))
        df[m] = df[col].map(lambda s, n=n: avg_growth(s, n)) if col in df else None
    return df


def sync_from_repo() -> dict:
    """Trae los datos que GitHub Actions prepara cada noche (rama «datos»), si son más nuevos que los locales."""
    try:
        from . import remoto
        done = remoto.sync_screener(BASE_FILE, PRICES_FILE)
        try:
            done.update(remoto.sync_europa(EU_BASE_FILE, EU_MARKET_FILE))
        except Exception:  # noqa: BLE001
            pass
        return done
    except Exception:  # noqa: BLE001
        return {"base": False, "market": False}


def save_base(df: pd.DataFrame):
    if "CIK" in df:
        df = df[pd.to_numeric(df["CIK"], errors="coerce").fillna(0) > 0]  # las europeas tienen su propio fichero
    df.to_pickle(BASE_FILE)


def _num(x):
    try:
        return float(str(x).replace("$", "").replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def refresh_market(progress=None) -> pd.DataFrame:
    """Precio, capitalización, sector e industria de TODAS las acciones de EE. UU. en una sola llamada
    (screener público de Nasdaq). Si falla, precios en lote con yfinance."""
    import requests
    if progress:
        progress(0.2, "Descargando precios y sectores (Nasdaq)…")
    df = pd.DataFrame()
    try:
        r = requests.get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true",
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=60)
        rows = r.json()["data"]["rows"]
        df = pd.DataFrame([{"Ticker": x["symbol"].strip().replace("/", "-").replace("^", "-P"), "Precio": _num(x.get("lastsale")),
                            "_mcap_nq": _num(x.get("marketCap")), "Sector": x.get("sector") or "—", "Industria": x.get("industry") or "—",
                            "País": x.get("country") or "—"} for x in rows])
    except Exception:  # noqa: BLE001
        df = pd.DataFrame()
    if df.empty:
        base = load_base(9999)
        tickers = list(base["Ticker"]) if base is not None else []
        out: dict[str, float] = {}
        for i in range(0, len(tickers), 400):
            if progress:
                progress(min((i + 400) / max(len(tickers), 1), 1.0), f"Precios {i + 1}-{min(i + 400, len(tickers))} (Yahoo)")
            out.update(prices.batch_last_prices(tickers[i:i + 400]))
        df = pd.DataFrame({"Ticker": list(out), "Precio": list(out.values())})
    if not df.empty:
        df.to_pickle(PRICES_FILE)
    return df


def load_market() -> tuple[pd.DataFrame | None, float | None]:
    if PRICES_FILE.exists():
        mk = pd.read_pickle(PRICES_FILE)
        eu = _load_eu(EU_MARKET_FILE)
        if eu is not None and not eu.empty:
            mk = pd.concat([mk[~mk["Ticker"].isin(eu["Ticker"])], eu], ignore_index=True)
        return mk, (time.time() - PRICES_FILE.stat().st_mtime) / 3600
    return None, None


def with_valuation(base: pd.DataFrame, mk: pd.DataFrame | None) -> pd.DataFrame:
    df = base.copy()
    if mk is None or mk.empty:
        for m in VALUATION:
            df[m] = None
        for c in ("Sector", "Industria", "País"):
            df[c] = "—"
        return df
    mk = mk.drop_duplicates("Ticker").set_index("Ticker")
    for c in ("Precio", "_mcap_nq", "Sector", "Industria", "País", "_fx_q", "_fx_r"):
        df[c] = df["Ticker"].map(mk[c]) if c in mk else None
    for c in ("Sector", "Industria", "País"):
        df[c] = df[c].fillna("—")
    # Europeas: precio en la divisa de cotización y cuentas en la del informe → todo a $ para comparar tamaños y ratios.
    fxq = pd.to_numeric(df["_fx_q"], errors="coerce").fillna(1.0)
    fxr = pd.to_numeric(df["_fx_r"], errors="coerce").fillna(1.0)
    eu = pd.to_numeric(df["_fx_r"], errors="coerce").notna()
    if eu.any():
        for c in ("_debt", "_cash", "_eq", "_fcf", "_op", "_ebitda", "_div", "_rev", "_ni"):
            df[c] = pd.to_numeric(df[c], errors="coerce") * fxr
        df.loc[eu, "Ventas (M$)"] = df.loc[eu, "_rev"] / 1e6
        df.loc[eu, "Beneficio (M$)"] = df.loc[eu, "_ni"] / 1e6
    mcap_calc = df["Precio"] * fxq * df["Acciones (M)"] * 1e6
    mcap = pd.to_numeric(df["_mcap_nq"], errors="coerce").where(lambda s: s > 0).fillna(mcap_calc)
    ev = mcap + df["_debt"].fillna(0) - df["_cash"].fillna(0)
    if eu.any():
        # cruce dudoso entre ticker y cuentas (o acciones mal etiquetadas): sin valoración antes que una valoración absurda
        ps_ratio = mcap / pd.to_numeric(df["_rev"], errors="coerce").where(lambda x: x > 0)
        bad = eu & ((mcap > 6e12) | (ps_ratio > 150))
        mcap = mcap.mask(bad)
        ev = ev.mask(bad)
        df.loc[bad, "Precio"] = None
    df["Capitalización (M$)"] = mcap / 1e6
    df["Valor empresa (M$)"] = ev / 1e6
    pos = lambda s: pd.to_numeric(s, errors="coerce").where(lambda x: x > 0)  # noqa: E731
    df["PER"] = (df["Precio"] * fxq) / pos(df["BPA"] * fxr)
    df["PEG"] = df["PER"] / (pos(df["CAGR BPA 5a"]) * 100)
    df["P/Ventas"] = mcap / pos(df["_rev"])
    df["P/Valor contable"] = mcap / pos(df["_eq"])
    df["P/FCF"] = mcap / pos(df["_fcf"])
    df["EV/EBIT"] = ev / pos(df["_op"])
    df["EV/EBITDA"] = ev / pos(df["_ebitda"])
    df["Rent. beneficio"] = (df["BPA"] * fxr) / (df["Precio"] * fxq)
    df["Rent. FCF"] = df["_fcf"] / mcap
    df["Rent. dividendo"] = df["_div"].fillna(0) / mcap
    return df


NOTAS_FILE = Path(__file__).resolve().parent.parent / "data" / "notas_financieras.csv.gz"
NOTA_COLS = ["Nota financiera", "Nota PyG", "Nota Balance", "Nota Cash Flow", "Nota Asignación de capital", "Preguntas no aplicables"]


def with_notas(df: pd.DataFrame) -> pd.DataFrame:
    """Añade las notas del examen financiero calculadas para todo el universo (GitHub Action semanal)."""
    if not NOTAS_FILE.exists():
        for c in NOTA_COLS:
            if c not in df:
                df[c] = None
        return df
    n = pd.read_csv(NOTAS_FILE, usecols=lambda c: c in NOTA_COLS + ["Ticker", "CIK"])
    n = n.drop_duplicates("CIK").set_index("CIK")
    for c in NOTA_COLS:
        us = df["CIK"].map(n[c]) if c in n else None
        df[c] = us if c not in df else (pd.Series(us, index=df.index).where(pd.to_numeric(df["CIK"], errors="coerce").fillna(0) > 0, df[c]))
    return df


def notas_age_days() -> float | None:
    return (time.time() - NOTAS_FILE.stat().st_mtime) / 86400 if NOTAS_FILE.exists() else None


def apply_filters(df: pd.DataFrame, filters: dict[str, tuple], exchanges: list[str] | None = None, text: str = "",
                  sectors: list[str] | None = None, industries: list[str] | None = None) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if exchanges:
        m &= df["Mercado"].isin(exchanges)
    if sectors and "Sector" in df:
        m &= df["Sector"].isin(sectors)
    if industries and "Industria" in df:
        m &= df["Industria"].isin(industries)
    if text:
        t = text.strip().lower()
        m &= df["Ticker"].str.lower().str.contains(t, regex=False) | df["Empresa"].str.lower().str.contains(t, regex=False)
    for col, (lo, hi) in filters.items():
        if col not in df:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if lo is not None:
            m &= s >= lo
        if hi is not None:
            m &= s <= hi
        if lo is not None or hi is not None:
            m &= s.notna()
    return df[m]


# compatibilidad con el lote / página antigua
def build_universe_metrics(progress=None, years_back: int = 10) -> pd.DataFrame:
    return build_base(progress, years_back)


Path(CACHE).mkdir(parents=True, exist_ok=True)
