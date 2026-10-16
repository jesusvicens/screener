"""Convierte los datos XBRL de la SEC en tus tres estados anuales (PyG, Balance, Cash Flow).

Mismas líneas que las hojas «PyG», «Balance» y «Cash Flow» de tu Excel. Millones de la divisa
de presentación (USD casi siempre), acciones en millones, BPA por acción.

Cada concepto tiene una lista de etiquetas XBRL alternativas: se usa la primera que exista
para cada año (las empresas cambian de etiqueta con los años). Lo que no aparece se deriva
de otras líneas cuando es posible (p. ej. margen bruto = ventas − coste de ventas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"}

# (clave, etiqueta en pantalla, tipo, [etiquetas XBRL us-gaap], [etiquetas IFRS])
# tipo: "flow" = flujo del ejercicio, "inst" = saldo a cierre, "ps" = por acción, "sh" = acciones
CONCEPTS: list[tuple[str, str, str, list[str], list[str]]] = [
    # --- PyG
    ("revenue", "Ventas", "flow", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                                   "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                                   "SalesRevenueGoodsNet", "SalesRevenueServicesNet", "RevenuesNetOfInterestExpense",
                                   "TotalRevenuesAndOtherIncome"], ["Revenue", "RevenueFromContractsWithCustomers"]),
    ("cogs", "Coste de ventas", "flow", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                                         "CostOfServices", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"],
     ["CostOfSales"]),
    ("gross_profit", "Margen bruto", "flow", ["GrossProfit"], ["GrossProfit"]),
    ("rnd", "I+D", "flow", ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                            "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost"],
     ["ResearchAndDevelopmentExpense"]),
    ("sga", "Gastos comerciales y generales (SG&A)", "flow", ["SellingGeneralAndAdministrativeExpense"],
     ["SellingGeneralAndAdministrativeExpense"]),
    ("_sm", "", "flow", ["SellingAndMarketingExpense"], ["SellingExpense", "DistributionCosts"]),
    ("_ga", "", "flow", ["GeneralAndAdministrativeExpense"], ["AdministrativeExpense"]),
    ("opex", "Gastos operativos", "flow", ["OperatingExpenses"], []),
    ("operating_income", "Resultado operativo (EBIT)", "flow", ["OperatingIncomeLoss"],
     ["ProfitLossFromOperatingActivities"]),
    ("nonop", "Resultado no operativo", "flow", ["NonoperatingIncomeExpense"], []),
    ("pretax", "Beneficio antes de impuestos", "flow",
     ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"], ["ProfitLossBeforeTax"]),
    ("taxes", "Impuestos", "flow", ["IncomeTaxExpenseBenefit"], ["IncomeTaxExpenseContinuingOperations"]),
    ("net_income", "Beneficio neto", "flow", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
     ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"]),
    ("shares_basic", "Acciones básicas (M)", "sh", ["WeightedAverageNumberOfSharesOutstandingBasic"],
     ["WeightedAverageShares"]),
    ("shares_diluted", "Acciones diluidas (M)", "sh", ["WeightedAverageNumberOfDilutedSharesOutstanding"],
     ["AdjustedWeightedAverageShares"]),
    ("eps_basic", "BPA básico", "ps", ["EarningsPerShareBasic"], ["BasicEarningsLossPerShare"]),
    ("eps_diluted", "BPA diluido", "ps", ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
     ["DilutedEarningsLossPerShare"]),
    # --- Balance
    ("cash_sti", "Caja e inversiones a corto", "inst", ["CashCashEquivalentsAndShortTermInvestments"], []),
    ("_cash", "", "inst", ["CashAndCashEquivalentsAtCarryingValue", "Cash",
                          "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], ["CashAndCashEquivalents"]),
    ("_sti", "", "inst", ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
                         "AvailableForSaleSecuritiesCurrent"], ["CurrentInvestments", "OtherCurrentFinancialAssets"]),
    ("receivables", "Clientes", "inst", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
                                        "AccountsNotesAndLoansReceivableNetCurrent"], ["TradeAndOtherCurrentReceivables"]),
    ("inventory", "Existencias", "inst", ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"], ["Inventories"]),
    ("prepaid", "Gastos anticipados", "inst", ["PrepaidExpenseAndOtherAssetsCurrent", "PrepaidExpenseCurrent"], []),
    ("other_current_assets", "Otros activos corrientes", "inst", ["OtherAssetsCurrent"], ["OtherCurrentAssets"]),
    ("current_assets", "Total activo corriente", "inst", ["AssetsCurrent"], ["CurrentAssets"]),
    ("ppe", "Inmovilizado material (PPE)", "inst", ["PropertyPlantAndEquipmentNet",
                                                    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization"],
     ["PropertyPlantAndEquipment"]),
    ("lt_investments", "Inversiones a largo plazo", "inst", ["LongTermInvestments", "MarketableSecuritiesNoncurrent",
                                                            "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"], []),
    ("_goodwill", "", "inst", ["Goodwill"], ["Goodwill"]),
    ("_intangibles", "", "inst", ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"],
     ["IntangibleAssetsOtherThanGoodwill"]),
    ("_gw_int", "", "inst", ["IntangibleAssetsNetIncludingGoodwill"], []),
    ("total_assets", "Total activo", "inst", ["Assets"], ["Assets"]),
    ("current_liabilities", "Total pasivo corriente", "inst", ["LiabilitiesCurrent"], ["CurrentLiabilities"]),
    ("st_debt", "Deuda a corto plazo", "inst", ["DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings",
                                               "LongTermDebtAndCapitalLeaseObligationsCurrent", "CommercialPaper"],
     ["CurrentBorrowings", "ShorttermBorrowings"]),
    ("lt_debt", "Deuda a largo plazo", "inst", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations",
                                               "LongTermDebt", "SeniorLongTermNotes", "LongTermNotesPayable",
                                               "UnsecuredLongTermDebt"], ["NoncurrentBorrowings", "LongtermBorrowings"]),
    ("other_lt_liabilities", "Otros pasivos a largo plazo", "inst", ["OtherLiabilitiesNoncurrent"], ["OtherNoncurrentLiabilities"]),
    ("total_liabilities", "Total pasivo", "inst", ["Liabilities"], ["Liabilities"]),
    ("treasury_stock", "Autocartera (acciones propias)", "inst", ["TreasuryStockValue", "TreasuryStockValueAcquiredCostMethod",
                                                                   "TreasuryStockCommonValue"], ["TreasuryShares"]),
    ("deferred_rev_current", "Ingresos diferidos a corto", "inst", ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"], []),
    ("interest_expense", "Gasto por intereses", "flow", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                                                         "InterestAndDebtExpense", "InterestPaidNet"], ["InterestExpense", "FinanceCosts"]),
    ("retained_earnings", "Reservas (beneficios retenidos)", "inst", ["RetainedEarningsAccumulatedDeficit"], ["RetainedEarnings"]),
    ("aoci", "Otro resultado global acumulado", "inst", ["AccumulatedOtherComprehensiveIncomeLossNetOfTax"], []),
    ("equity", "Patrimonio neto", "inst", ["StockholdersEquity",
                                          "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
     ["EquityAttributableToOwnersOfParent", "Equity"]),
    ("liabilities_equity", "Total pasivo y patrimonio", "inst", ["LiabilitiesAndStockholdersEquity"], ["EquityAndLiabilities"]),
    ("shares_outstanding", "Acciones en circulación al cierre (M)", "sh_inst",
     ["CommonStockSharesOutstanding"], []),
    # --- Cash Flow
    ("cf_net_income", "Beneficio neto (flujo)", "flow", ["ProfitLoss", "NetIncomeLoss"], ["ProfitLoss"]),
    ("da", "Amortizaciones", "flow", ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                                      "DepreciationAndAmortization", "Depreciation"],
     ["DepreciationAndAmortisationExpense", "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"]),
    ("sbc", "Remuneración en acciones", "flow", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
     ["AdjustmentsForSharebasedPayments"]),
    ("_inc_receivables", "", "flow", ["IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInReceivables",
                                     "IncreaseDecreaseInAccountsAndNotesReceivable"], []),
    ("_inc_inventory", "", "flow", ["IncreaseDecreaseInInventories"], []),
    ("chg_payables", "Variación de proveedores", "flow", ["IncreaseDecreaseInAccountsPayable",
                                                        "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities"], []),
    ("ocf", "Flujo de caja operativo", "flow", ["NetCashProvidedByUsedInOperatingActivities",
                                               "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
     ["CashFlowsFromUsedInOperatingActivities"]),
    ("_capex_pos", "", "flow", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
                               "PaymentsForCapitalImprovements", "PaymentsToAcquireOtherPropertyPlantAndEquipment"],
     ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]),
    ("_acq_pos", "", "flow", ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"], []),
    ("icf", "Flujo de caja de inversión", "flow", ["NetCashProvidedByUsedInInvestingActivities",
                                                  "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"],
     ["CashFlowsFromUsedInInvestingActivities"]),
    ("_debt_issued", "", "flow", ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt",
                                 "ProceedsFromDebtNetOfIssuanceCosts", "ProceedsFromIssuanceOfSeniorLongTermDebt",
                                 "ProceedsFromIssuanceOfUnsecuredDebt"], []),
    ("_debt_repaid", "", "flow", ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "RepaymentsOfSeniorDebt",
                                 "RepaymentsOfUnsecuredDebt"], []),
    ("_st_debt_net", "", "flow", ["ProceedsFromRepaymentsOfShortTermDebt", "ProceedsFromRepaymentsOfCommercialPaper"], []),
    ("_buyback_pos", "", "flow", ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
     ["PaymentsToAcquireOrRedeemEntitysShares"]),
    ("_equity_issued", "", "flow", ["ProceedsFromIssuanceOfCommonStock", "ProceedsFromSaleOfTreasuryStock",
                                   "ProceedsFromStockOptionsExercised",
                                   "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans"],
     ["ProceedsFromIssuingShares"]),
    ("_dividends_pos", "", "flow", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
     ["DividendsPaidClassifiedAsFinancingActivities"]),
    ("fcf_fin", "Flujo de caja de financiación", "flow", ["NetCashProvidedByUsedInFinancingActivities",
                                                        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"],
     ["CashFlowsFromUsedInFinancingActivities"]),
    ("net_cash_flow", "Variación neta de caja", "flow",
     ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
      "CashAndCashEquivalentsPeriodIncreaseDecrease"], ["IncreaseDecreaseInCashAndCashEquivalents"]),
]

PYG_ROWS = ["revenue", "cogs", "gross_profit", "rnd", "sga", "opex", "operating_income", "nonop", "pretax", "taxes",
            "net_income", "da", "ebitda", "shares_basic", "shares_diluted", "eps_basic", "eps_diluted"]
BALANCE_ROWS = ["cash_sti", "receivables", "inventory", "prepaid", "other_current_assets", "current_assets", "ppe",
                "lt_investments", "goodwill_intangibles", "other_lt_assets", "lt_assets", "total_assets",
                "current_liabilities", "st_debt", "lt_debt", "other_lt_liabilities", "lt_liabilities",
                "total_liabilities", "retained_earnings", "aoci", "equity", "liabilities_equity", "shares_outstanding"]
CASHFLOW_ROWS = ["cf_net_income", "da", "sbc", "chg_receivables", "chg_inventory", "chg_payables", "ocf", "capex",
                 "acquisitions", "icf", "debt_net", "equity_net", "dividends", "fcf_fin", "net_cash_flow", "fcf"]

LABELS = {k: lbl for k, lbl, *_ in CONCEPTS if lbl}
LABELS.update({
    "ebitda": "EBITDA", "goodwill_intangibles": "Fondo de comercio e intangibles", "other_lt_assets": "Otros activos a largo plazo",
    "lt_assets": "Total activo no corriente", "lt_liabilities": "Total pasivo no corriente",
    "chg_receivables": "Variación de clientes", "chg_inventory": "Variación de existencias", "capex": "Capex",
    "acquisitions": "Adquisiciones netas", "debt_net": "Emisión (+) / devolución (−) de deuda",
    "equity_net": "Emisión (+) / recompra (−) de acciones", "dividends": "Dividendos pagados",
    "fcf": "Flujo de caja libre (OCF + capex)", "debt_issued": "Deuda emitida", "debt_repaid": "Deuda devuelta",
    "buybacks": "Recompras brutas",
})


@dataclass
class Financials:
    ticker: str
    name: str
    cik: int
    currency: str
    years: list[int]
    period_end: dict[int, str]
    data: dict[str, dict[int, float]]
    sources: dict[str, dict[int, str]] = field(default_factory=dict)  # qué etiqueta XBRL se usó
    warnings: list[str] = field(default_factory=list)

    # acceso cómodo: f["revenue"][2025]
    def __getitem__(self, key: str) -> dict[int, float]:
        return self.data.get(key, {})

    def get(self, key: str, year: int, default=None):
        v = self.data.get(key, {}).get(year)
        return default if v is None else v

    def series(self, key: str) -> list[float | None]:
        return [self.data.get(key, {}).get(y) for y in self.years]

    def table(self, rows: list[str]) -> pd.DataFrame:
        df = pd.DataFrame({y: [self.data.get(r, {}).get(y) for r in rows] for y in self.years}, index=[LABELS.get(r, r) for r in rows])
        df.index.name = f"Millones de {self.currency} (acciones en M, BPA por acción)"
        return df

    def to_dict(self) -> dict:
        return {"ticker": self.ticker, "name": self.name, "cik": self.cik, "currency": self.currency,
                "years": self.years, "period_end": self.period_end, "data": self.data}


def _fiscal_year(end: str) -> int:
    d = date.fromisoformat(end)
    # Ejercicios de 52/53 semanas que acaban en los primeros días de enero pertenecen al año anterior.
    return d.year - 1 if (d.month == 1 and d.day <= 7) else d.year


def _annual_values(facts: dict, taxonomy: str, tag: str, kind: str) -> tuple[dict[int, float], str | None, dict[int, str]]:
    node = facts.get("facts", {}).get(taxonomy, {}).get(tag)
    if not node:
        return {}, None, {}
    units = node.get("units", {})
    if kind in ("sh", "sh_inst"):
        unit = "shares" if "shares" in units else next(iter(units), None)
    elif kind == "ps":
        unit = next((u for u in units if "/shares" in u), None)
    else:
        unit = "USD" if "USD" in units else next((u for u in units if "/" not in u and u not in ("shares", "pure")), None)
    if unit is None:
        return {}, None, {}
    best: dict[int, tuple[str, str, float]] = {}  # año -> (fin, presentado, valor)
    for x in units[unit]:
        if x.get("form") not in ANNUAL_FORMS:
            continue
        end = x.get("end")
        if not end:
            continue
        if kind in ("flow", "ps", "sh"):
            if "start" not in x:
                continue
            days = (date.fromisoformat(end) - date.fromisoformat(x["start"])).days
            if not 340 <= days <= 380:
                continue
        elif "start" in x:
            continue
        fy = _fiscal_year(end)
        cand = (end, x.get("filed", ""), float(x["val"]))
        cur = best.get(fy)
        # Para cada ejercicio: el periodo que termina más tarde y, dentro de él, el dato presentado más reciente.
        if cur is None or (cand[0], cand[1]) > (cur[0], cur[1]):
            best[fy] = cand
    vals = {fy: v[2] for fy, v in best.items()}
    ends = {fy: v[0] for fy, v in best.items()}
    return vals, unit, ends


SPLIT_FACTORS = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 15, 1 / 20, 1 / 25, 1 / 30, 1 / 50]


def detect_split(ratio: float | None) -> float | None:
    """Si el número de acciones salta de un año a otro como en un split (×2, ×4, ÷10...), devuelve el factor."""
    if not ratio or 0.6 < ratio < 1.7:
        return None
    best = min(SPLIT_FACTORS, key=lambda f: abs(ratio / f - 1))
    return best if abs(ratio / best - 1) < 0.12 else None


def _adjust_splits(out: dict, years: list[int]) -> list[str]:
    """Los 10-K antiguos no están ajustados por splits posteriores: lo corregimos para BPA y acciones."""
    notes = []
    sh = out.get("shares_diluted", {})
    for i in range(1, len(years)):
        a, b = sh.get(years[i - 1]), sh.get(years[i])
        f = detect_split(b / a if (a and b) else None)
        if f:
            for y in years[:i]:
                for k in ("shares_basic", "shares_diluted", "shares_outstanding"):
                    if y in out.get(k, {}):
                        out[k][y] *= f
                for k in ("eps_basic", "eps_diluted"):
                    if y in out.get(k, {}):
                        out[k][y] /= f
            txt = f"{f:g}:1" if f >= 1 else f"1:{1 / f:g}"
            notes.append(f"Split {txt} detectado en {years[i]}: BPA y acciones de años anteriores ajustados.")
    return notes


def build(facts: dict, ticker: str, n_years: int = 10) -> Financials:
    raw: dict[str, dict[int, float]] = {}
    src: dict[str, dict[int, str]] = {}
    period_end: dict[int, str] = {}
    currency = "USD"
    currency_votes: dict[str, int] = {}
    has_usgaap = bool(facts.get("facts", {}).get("us-gaap"))

    for key, _lbl, kind, gaap_tags, ifrs_tags in CONCEPTS:
        tags = [("us-gaap", t) for t in gaap_tags] if has_usgaap else []
        tags += [("ifrs-full", t) for t in ifrs_tags]
        merged: dict[int, float] = {}
        used: dict[int, str] = {}
        for tax, tag in tags:
            vals, unit, ends = _annual_values(facts, tax, tag, kind)
            for fy, v in vals.items():
                if fy not in merged:
                    merged[fy] = v
                    used[fy] = f"{tax}:{tag}"
                    if kind == "flow" and key in ("revenue", "net_income", "ocf") and fy not in period_end:
                        period_end[fy] = ends[fy]
            if unit and kind == "flow" and vals:
                currency_votes[unit] = currency_votes.get(unit, 0) + len(vals)
        raw[key] = merged
        src[key] = used
    if currency_votes:
        currency = max(currency_votes, key=currency_votes.get)

    # Años disponibles: los que tienen ventas o beneficio neto.
    years_all = sorted(set(raw["revenue"]) | set(raw["net_income"]))
    years = years_all[-n_years:]
    M = 1e6

    def g(k, y):
        return raw.get(k, {}).get(y)

    out: dict[str, dict[int, float]] = {}

    def put(k, y, v):
        if v is not None:
            out.setdefault(k, {})[y] = v

    for y in years:
        rev = g("revenue", y)
        cogs = g("cogs", y)
        gp = g("gross_profit", y)
        if gp is None and rev is not None and cogs is not None:
            gp = rev - cogs
        if cogs is None and rev is not None and gp is not None:
            cogs = rev - gp
        if gp is None and rev is not None and cogs is None:
            gp, cogs = rev, 0.0  # sin coste de ventas separado (bancos, servicios): margen bruto = ventas
        sga = g("sga", y)
        if sga is None and (g("_sm", y) is not None or g("_ga", y) is not None):
            sga = (g("_sm", y) or 0) + (g("_ga", y) or 0)
        op = g("operating_income", y)
        opex = g("opex", y)
        if opex is None and gp is not None and op is not None:
            opex = gp - op
        if op is None and gp is not None and opex is not None:
            op = gp - opex
        pretax = g("pretax", y)
        ni = g("net_income", y)
        taxes = g("taxes", y)
        if pretax is None and ni is not None and taxes is not None:
            pretax = ni + taxes
        nonop = g("nonop", y)
        if pretax is not None and op is not None:
            nonop = pretax - op  # así cuadra siempre EBIT + no operativo = BAI
        da = g("da", y)
        for k, v in [("revenue", rev), ("cogs", cogs), ("gross_profit", gp), ("rnd", g("rnd", y)), ("sga", sga),
                     ("opex", opex), ("operating_income", op), ("nonop", nonop), ("pretax", pretax), ("taxes", taxes),
                     ("net_income", ni), ("da", da)]:
            put(k, y, None if v is None else v / M)
        if op is not None and da is not None:
            put("ebitda", y, (op + da) / M)
        sb, sd = g("shares_basic", y), g("shares_diluted", y)
        if sd is None:
            sd = sb
        put("shares_basic", y, None if sb is None else sb / M)
        put("shares_diluted", y, None if sd is None else sd / M)
        epsd = g("eps_diluted", y)
        if epsd is None and ni is not None and sd:
            epsd = ni / sd
        epsb = g("eps_basic", y)
        if epsb is None and ni is not None and sb:
            epsb = ni / sb
        put("eps_basic", y, epsb)
        put("eps_diluted", y, epsd)

        # --- Balance
        cash = g("cash_sti", y)
        if cash is None and g("_cash", y) is not None:
            cash = g("_cash", y) + (g("_sti", y) or 0)
        ta, ca, cl = g("total_assets", y), g("current_assets", y), g("current_liabilities", y)
        gw = g("_gw_int", y)
        if gw is None and (g("_goodwill", y) is not None or g("_intangibles", y) is not None):
            gw = (g("_goodwill", y) or 0) + (g("_intangibles", y) or 0)
        eq = g("equity", y)
        tl = g("total_liabilities", y)
        le = g("liabilities_equity", y) or ta
        if tl is None and le is not None and eq is not None:
            tl = le - eq
        lta = ta - ca if (ta is not None and ca is not None) else None
        other_lta = None
        if lta is not None:
            other_lta = lta - (g("ppe", y) or 0) - (g("lt_investments", y) or 0) - (gw or 0)
        ltl = tl - cl if (tl is not None and cl is not None) else None
        for k, v in [("cash_sti", cash), ("receivables", g("receivables", y)), ("inventory", g("inventory", y)),
                     ("prepaid", g("prepaid", y)), ("other_current_assets", g("other_current_assets", y)),
                     ("current_assets", ca), ("ppe", g("ppe", y)), ("lt_investments", g("lt_investments", y)),
                     ("goodwill_intangibles", gw), ("other_lt_assets", other_lta), ("lt_assets", lta), ("total_assets", ta),
                     ("current_liabilities", cl), ("st_debt", g("st_debt", y)), ("lt_debt", g("lt_debt", y)),
                     ("other_lt_liabilities", g("other_lt_liabilities", y)), ("lt_liabilities", ltl),
                     ("total_liabilities", tl), ("retained_earnings", g("retained_earnings", y)), ("aoci", g("aoci", y)),
                     ("equity", eq), ("liabilities_equity", le)]:
            put(k, y, None if v is None else v / M)
        so = g("shares_outstanding", y)
        put("shares_outstanding", y, None if so is None else so / M)
        for k in ("treasury_stock", "deferred_rev_current", "interest_expense"):
            v = g(k, y)
            put(k, y, None if v is None else abs(v) / M)

        # --- Cash Flow
        cfni = g("cf_net_income", y) or ni
        capex = -g("_capex_pos", y) if g("_capex_pos", y) is not None else None
        acq = -g("_acq_pos", y) if g("_acq_pos", y) is not None else None
        debt_net = None
        if any(g(k, y) is not None for k in ("_debt_issued", "_debt_repaid", "_st_debt_net")):
            debt_net = (g("_debt_issued", y) or 0) - (g("_debt_repaid", y) or 0) + (g("_st_debt_net", y) or 0)
        eq_net = None
        if g("_buyback_pos", y) is not None or g("_equity_issued", y) is not None:
            eq_net = (g("_equity_issued", y) or 0) - (g("_buyback_pos", y) or 0)
        divs = -g("_dividends_pos", y) if g("_dividends_pos", y) is not None else None
        ocf = g("ocf", y)
        fcf = ocf + (capex or 0) if ocf is not None else None
        for k, v in [("cf_net_income", cfni), ("sbc", g("sbc", y)),
                     ("chg_receivables", None if g("_inc_receivables", y) is None else -g("_inc_receivables", y)),
                     ("chg_inventory", None if g("_inc_inventory", y) is None else -g("_inc_inventory", y)),
                     ("chg_payables", g("chg_payables", y)), ("ocf", ocf), ("capex", capex), ("acquisitions", acq),
                     ("icf", g("icf", y)), ("debt_net", debt_net), ("equity_net", eq_net), ("dividends", divs),
                     ("fcf_fin", g("fcf_fin", y)), ("net_cash_flow", g("net_cash_flow", y)), ("fcf", fcf),
                     ("debt_issued", g("_debt_issued", y)), ("debt_repaid", g("_debt_repaid", y)),
                     ("buybacks", g("_buyback_pos", y))]:
            put(k, y, None if v is None else v / M)

    warnings = _adjust_splits(out, years)
    for k in ("revenue", "net_income", "operating_income", "equity", "ocf", "eps_diluted", "shares_diluted"):
        miss = [y for y in years if out.get(k, {}).get(y) is None]
        if miss:
            warnings.append(f"Falta «{LABELS.get(k, k)}» en: {', '.join(map(str, miss))}")
    if len(years) < 5:
        warnings.append(f"Solo hay {len(years)} ejercicios anuales en XBRL (la SEC tiene datos estructurados desde ~2009).")

    return Financials(ticker=ticker.upper(), name=facts.get("entityName", ticker), cik=int(facts.get("cik", 0)),
                      currency=currency, years=years, period_end={y: period_end.get(y, "") for y in years},
                      data=out, sources=src, warnings=warnings)
