"""Análisis de riesgo de la inversión (método «Parte II · El riesgo»).

Réplica del bloque «Análisis de riesgo» de tu hoja Modelo EPS (filas 31-126):
resumen de BPA y precio de salida, distribución de valores futuros, test de cobertura con
probabilidades de prueba (paso 10: engordar la cola izquierda), ventana de horizontes,
valor estimado y precios de compra, test de exposición por perfil de inversor, preguntas
de supervivencia y conclusión.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .analysis import SCENARIOS, InvestorParams, Valuation

DEFAULT_TEST_PROBS = {"Optimista": 0.15, "Base": 0.40, "Adverso": 0.30, "Desastre": 0.15}
DEFAULT_TEST_PRICES = [200.0, 300.0, 450.0]
DEFAULT_DROP = -0.45
DEFAULT_MIN_GUARANTEE = 0.30
DEFAULT_PROFILES = [
    {"Inversor": "A · posición pequeña sin deuda", "Peso": 0.10, "Deuda / capital": 0.0, "Lectura": "Riesgo patrimonial limitado"},
    {"Inversor": "B · posición grande sin deuda", "Peso": 0.70, "Deuda / capital": 0.0, "Lectura": "Riesgo patrimonial elevado, conserva el control del tiempo"},
    {"Inversor": "C · apalancado (50 % propio + 50 % deuda)", "Peso": 1.00, "Deuda / capital": 1.0, "Lectura": "La deuda amplifica el resultado y puede quitar el control del tiempo"},
    {"Inversor": "B ajustado por aversión (reduce al 30 %)", "Peso": 0.30, "Deuda / capital": 0.0, "Lectura": "Mismo negocio y probabilidades; menos daño en el desastre"},
    {"Inversor": "C ajustado por aversión (sin deuda)", "Peso": 1.00, "Deuda / capital": 0.0, "Lectura": "Elimina el mecanismo que podía forzar la venta"},
]
SURVIVAL_QUESTIONS = [
    "¿Quién puede obligarme a vender? ¿Qué tendría que ocurrir para que lo hiciera?",
    "¿Hay deuda ligada al valor de la posición? ¿Tendría que aportar capital tras una caída?",
    "¿Necesitaré este dinero antes del horizonte de la tesis (ver ventana)?",
    "¿Pueden fallar mis otras fuentes de ingresos o liquidez en el mismo escenario (empleo, sector, cartera)?",
    "¿De cuántas fuentes económicas distintas depende realmente mi patrimonio?",
]


def _verdict(x: float) -> str:
    x = round(x, 6)
    return "Compensa" if x > 0 else ("Equilibrio" if x == 0 else "No compensa")


def _cov(opp: float, risk: float):
    return opp / risk if risk > 0 else "Sin cola izquierda"


def _es(x: float, d: int = 2) -> str:
    """Número con formato español (coma decimal), como FIXED() en tu Excel."""
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class RiskResult:
    exit_summary: pd.DataFrame
    distribution: pd.DataFrame
    coverage: dict
    coverage_test: dict
    window_summary: dict
    value: dict
    price_table: pd.DataFrame
    exposure: pd.DataFrame
    conclusion: list[str]


def analyze_risk(val: Valuation, params: InvestorParams, test_probs: dict | None = None, test_prices: list | None = None,
                 drop: float = DEFAULT_DROP, min_guarantee: float = DEFAULT_MIN_GUARANTEE, profiles: list | None = None) -> RiskResult:
    P, r, n = params.price, params.r, max(1, min(10, int(params.n)))
    test_probs = {**DEFAULT_TEST_PROBS, **(test_probs or {})}
    test_prices = [x for x in (test_prices if test_prices is not None else DEFAULT_TEST_PRICES) if x]
    profiles = profiles if profiles is not None else DEFAULT_PROFILES
    by = val.by_scenario

    # --- Resumen BPA futuro y precio de salida (5 y 10 años)
    rows = []
    for years in (5, 10):
        for scn in SCENARIOS:
            df = val.projections[scn]
            col = df.columns[years]
            eps = df.at["BPA diluido", col]
            per = val.scenarios[scn]["per_exit"]
            exit_p = eps * per
            rows.append({"Escenario": scn, "Años": years, "BPA": eps, "PER de salida": per, "Precio de salida": exit_p,
                         "Rentabilidad anual vs precio actual": (exit_p / P) ** (1 / years) - 1 if exit_p > 0 else -1.0})
    exit_summary = pd.DataFrame(rows)

    # --- 2. Distribución
    U = P * (1 + r) ** n
    vf = {s: by.at["Valor futuro (VF)", s] for s in SCENARIOS}
    p = {s: val.scenarios[s]["prob"] for s in SCENARIOS}
    F = {s: vf[s] - U for s in SCENARIOS}
    G = {s: p[s] * F[s] for s in SCENARIOS}
    neg = sum(g for g in G.values() if g < 0)
    K = {s: test_probs[s] * F[s] for s in SCENARIOS}
    dist = pd.DataFrame({s: {"Valor futuro (VF)": vf[s], "Probabilidad": p[s], "Rentabilidad anual": (vf[s] / P) ** (1 / n) - 1 if vf[s] > 0 else -1.0,
                             "Exceso (+) / déficit (−) vs umbral": F[s], "Ponderado por probabilidad": G[s],
                             "% del riesgo asumido": (G[s] / neg) if G[s] < 0 else 0.0,
                             "Probabilidad de prueba": test_probs[s], "Ponderado (prueba)": K[s]} for s in SCENARIOS})
    EVF = sum(p[s] * vf[s] for s in SCENARIOS)
    dist["Total / media"] = [EVF, sum(p.values()), (EVF / P) ** (1 / n) - 1 if EVF > 0 else -1.0, None, sum(G.values()),
                             1.0 if neg < 0 else 0.0, sum(test_probs.values()), sum(K.values())]

    # --- 3. Test de cobertura
    risk_p = sum(p[s] for s in SCENARIOS if F[s] < 0)
    risk = -sum(g for g in G.values() if g < 0)
    opp = sum(g for g in G.values() if g > 0)
    cov = _cov(opp, risk)
    coverage = {
        "Umbral: VF requerido = P × (1 + r)^n": U, "Valor futuro esperado E[VF]": EVF,
        "Riesgo de no compensación": risk_p, "Riesgo asumido (déficit esperado)": risk,
        "Déficit medio cuando no compensa": (risk / risk_p) if risk_p else 0.0,
        "Oportunidad asumida (exceso esperado)": opp, "Valor asumido (oportunidad − riesgo)": opp - risk,
        "Cobertura asumida (oportunidad / riesgo)": cov, "Veredicto": _verdict(opp - risk),
        "Valor asumido traído a hoy (por acción)": (opp - risk) / (1 + r) ** n,
        "Holgura: el riesgo podría ser mayor en": (cov - 1) if isinstance(cov, float) else 0.0,
        "Holgura: la oportunidad podría caer": (1 - 1 / cov) if isinstance(cov, float) and cov else 0.0,
    }
    t_risk = -sum(k for k in K.values() if k < 0)
    t_opp = sum(k for k in K.values() if k > 0)
    coverage_test = {"Riesgo de no compensación (prueba)": sum(test_probs[s] for s in SCENARIOS if F[s] < 0),
                     "Riesgo asumido (prueba)": t_risk, "Oportunidad asumida (prueba)": t_opp,
                     "Cobertura (prueba)": _cov(t_opp, t_risk)}

    # --- 4. Ventana
    inside = [int(c) for c in val.window.columns if val.window.at["¿Dentro de la ventana?", c] == "Sí"]
    window_summary = {"Primer año dentro de la ventana": inside[0] if inside else "Ninguno",
                      "Años dentro de la ventana (de 10)": len(inside)}

    # --- 5. Valor estimado y precios de compra
    V = EVF / (1 + r) ** n
    max_p = V * (1 - params.mos)
    value = {"Valor estimado hoy = E[VF] / (1 + r)^n": V, "Margen de seguridad al precio actual": (V - P) / V if V else None,
             "Rentabilidad anual implícita en la media": (EVF / P) ** (1 / n) - 1 if EVF > 0 else -1.0,
             "Precio máximo de compra con tu margen": max_p, "Precio actual frente al precio máximo": P / max_p - 1 if max_p > 0 else None}
    prices = [("Actual", P), ("Precio máx.", max_p), ("Equilibrio", V)] + [("Prueba", x) for x in test_prices]
    prow = []
    for lbl, B in prices:
        Ub = B * (1 + r) ** n
        rk = sum(p[s] * (Ub - vf[s]) for s in SCENARIOS if vf[s] < Ub)
        op = sum(p[s] * (vf[s] - Ub) for s in SCENARIOS if vf[s] > Ub)
        prow.append({"": lbl, "Precio de compra": B, "Margen frente al valor estimado": (V - B) / V if V else None,
                     "Umbral a n años": Ub, "Riesgo asumido": rk, "Oportunidad asumida": op, "Cobertura": _cov(op, rk),
                     "Veredicto": _verdict(op - rk)})
    price_table = pd.DataFrame(prow).set_index("")

    # --- 6. Test de exposición
    erows = []
    for pr in profiles:
        w, d = float(pr.get("Peso") or 0), float(pr.get("Deuda / capital") or 0)
        row = {"Inversor": pr.get("Inversor", ""), "Peso en el patrimonio": w, "Deuda / capital propio": d}
        for s in SCENARIOS:
            row[s] = w * (1 + d) * (vf[s] / P - 1)
        row["Pérdida temporal en la caída intermedia"] = w * (1 + d) * drop
        denom = (1 + d) * (1 + drop)
        eq_ratio = ((1 + d) * (1 + drop) - d) / denom if denom else -1.0
        row["Capital propio / posición tras la caída"] = eq_ratio
        row["Riesgo de supervivencia"] = "Bajo" if d == 0 else ("Muy alto" if eq_ratio <= 0 else ("Alto" if eq_ratio < min_guarantee else "Moderado"))
        row["Lectura"] = pr.get("Lectura", "")
        erows.append(row)
    exposure = pd.DataFrame(erows)

    # --- 8. Conclusión (mismo texto que tu Excel)
    cov_txt = _es(cov) if isinstance(cov, float) else cov
    shares = {s: dist.at["% del riesgo asumido", s] for s in SCENARIOS}
    worst = max(shares, key=shares.get)
    tcov = coverage_test["Cobertura (prueba)"]
    conclusion = [
        f"A {_es(P)} USD y exigiendo un {_es(r * 100, 1)} % anual a {n} años, la inversión {coverage['Veredicto'].lower()}: "
        f"cobertura {cov_txt}, riesgo de no compensación {_es(risk_p * 100, 0)} % y déficit medio de {_es(coverage['Déficit medio cuando no compensa'], 0)} USD cuando se falla.",
        f"Valor estimado {_es(V)} USD; margen de seguridad al precio actual {_es(value['Margen de seguridad al precio actual'] * 100, 1)} % "
        f"(exigido {_es(params.mos * 100, 0)} %). Precio máximo de compra: {_es(max_p)} USD. Rentabilidad anual implícita en la media: "
        f"{_es(value['Rentabilidad anual implícita en la media'] * 100, 1)} %.",
        (f"El {_es(shares[worst] * 100, 0)} % del riesgo asumido procede del escenario {worst}. " if shares[worst] > 0 else "Ningún escenario queda por debajo del umbral. ")
        + f"Con la cola izquierda engordada (probabilidades de prueba) la cobertura sería {_es(tcov) if isinstance(tcov, float) else tcov}.",
        "Advertencia: el veredicto depende de la distribución estimada (sobre todo del PER de salida de cada escenario). "
        "Si la cobertura es muy alta, revisa primero si la cola izquierda está completa.",
    ]
    return RiskResult(exit_summary, dist, coverage, coverage_test, window_summary, value, price_table, exposure, conclusion)
