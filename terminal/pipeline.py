"""Une todo: descarga → estados → análisis → valoración. Lo usa la ficha de empresa y el lote."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import analysis as A, exam as E, financials as F, prices, sec


@dataclass
class CompanyAnalysis:
    meta: dict
    fin: F.Financials
    hist: pd.Series
    avg_prices: dict
    stats: dict
    eps_df: pd.DataFrame
    roic_df: pd.DataFrame
    params: A.InvestorParams
    phase: str
    proposed: dict
    scenarios: dict
    val: A.Valuation | None
    suggestions: dict
    answers: dict
    score: dict
    saved: dict


def load_company(ticker: str, n_years: int = 10) -> tuple[dict, F.Financials, pd.Series]:
    from . import esef
    meta = None if esef.is_european(ticker) else sec.find(ticker)
    if not meta:
        meta = esef.find(ticker)
        if not meta:
            raise ValueError(f"No encuentro «{ticker}» ni en la SEC ni entre las cotizadas europeas.")
        facts = esef.company_facts(meta["lei"], meta["name"])
        fin = F.build(facts, meta["ticker"], n_years=n_years)
        fin.name = meta["name"]
        if facts.get("informes") is not None and len(fin.years) < 8:
            fin.warnings.append(f"Empresa europea: {len(fin.years)} ejercicios en formato ESEF (obligatorio en la UE desde 2020; "
                                "cada informe trae también el año anterior).")
        if not any(fin.get("shares_diluted", y) for y in fin.years):
            try:  # el informe no trae nº de acciones ni BPA: las acciones actuales de Yahoo para todos los años
                import yfinance as yf
                sh = yf.Ticker(meta["ticker"]).fast_info.get("shares")
            except Exception:  # noqa: BLE001
                sh = None
            if sh:
                for y in fin.years:
                    fin.data.setdefault("shares_diluted", {})[y] = sh / 1e6
                    ni = fin.get("net_income", y)
                    if ni is not None and fin.get("eps_diluted", y) is None:
                        fin.data.setdefault("eps_diluted", {})[y] = ni / (sh / 1e6)
                fin.warnings = [w for w in fin.warnings if "BPA" not in w and "Acciones" not in w] + [
                    f"El informe no etiqueta el nº de acciones: BPA calculado con las {sh / 1e6:,.0f} M de acciones actuales "
                    "(Yahoo) para todos los años; si ha habido recompras, el BPA antiguo sale algo bajo."]
        hist = prices.history(meta["ticker"], years=n_years + 2)
        return meta, fin, hist
    facts = sec.company_facts(meta["cik"])
    fin = F.build(facts, meta["ticker"], n_years=n_years)
    hist = prices.history(meta["ticker"], years=n_years + 2)
    return meta, fin, hist


def analyze(meta: dict, fin: F.Financials, hist: pd.Series, saved: dict | None = None,
            price_override: float | None = None, auto_financial_answers: bool = True) -> CompanyAnalysis:
    saved = saved or {}
    params = A.params_from_dict(saved.get("params"))
    last, last_date = prices.last_price(hist)
    if price_override:
        params.price = price_override
    elif not saved.get("precio_manual") or not params.price:
        if last:
            params.price, params.price_date = last, last_date
    if params.acciones_manual and fin.get("eps_diluted", fin.years[-1]) is None:
        import copy
        fin = copy.deepcopy(fin)
        for y in fin.years:
            ni = fin.get("net_income", y)
            if fin.get("eps_diluted", y) is None and ni is not None:
                fin.data.setdefault("shares_diluted", {})[y] = params.acciones_manual
                fin.data.setdefault("eps_diluted", {})[y] = ni / params.acciones_manual
        fin.warnings = [w for w in fin.warnings if "BPA" not in w and "Acciones" not in w] + [
            f"BPA calculado con {params.acciones_manual:,.0f} M de acciones escritas a mano para todos los años sin dato."]
    avg = prices.fiscal_year_average(hist, fin.period_end)
    stats = A.history_stats(fin)
    eps_df = A.eps_model(fin, avg)
    roic_df = A.roic(fin, params.rd_life)
    phase = saved.get("fase") or stats["phase"]
    proposed = A.propose_scenarios(stats, params, phase)
    scenarios = A.merge_overrides(proposed, saved.get("supuestos"), params, stats)
    val = None
    if params.price and fin.get("eps_diluted", fin.years[-1]) is not None:
        val = A.valuation(fin, stats, scenarios, params)
    sugg = E.suggestions(fin, stats)
    answers = dict(saved.get("examen") or {})
    if auto_financial_answers:
        for qid, (pts, _why) in sugg.items():
            answers.setdefault(qid, pts)
    sc = E.score(answers)
    return CompanyAnalysis(meta, fin, hist, avg, stats, eps_df, roic_df, params, phase, proposed, scenarios, val, sugg,
                           answers, sc, saved)


def summary_row(ca: CompanyAnalysis) -> dict:
    f, v = ca.fin, ca.val
    L = f.years[-1]
    eps = f.get("eps_diluted", L)
    row = {
        "Ticker": f.ticker, "Empresa": f.name, "Fase": ca.phase, "Precio": ca.params.price,
        "PER": (ca.params.price / eps) if (ca.params.price and eps and eps > 0) else None,
        "CAGR ventas 3a": ca.stats.get("g3"), "Margen operativo": ca.stats.get("om_last"), "ROE 5a": ca.stats.get("roe5"),
        "ROIC": ca.roic_df.loc["ROIC"].iloc[-1] if "ROIC" in ca.roic_df.index else None,
        "Nota financiera": ca.score["financiera"],
        "Nota final": ca.score["final"] if ca.score["cual_respondidas"] else None,
    }
    if v and v.value:
        row.update({"Valor estimado": v.value["Valor estimado hoy = E[VF] / (1+r)^n"],
                    "Margen de seguridad": v.value["Margen de seguridad al precio actual"],
                    "Rentab. implícita": v.value["Rentabilidad anual implícita en la media"],
                    "Prob. no compensar": v.coverage.get("Riesgo de no compensación (prob. de no llegar al umbral)"),
                    "Veredicto": v.coverage.get("Veredicto")})
    return row
