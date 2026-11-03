"""Opciones y acciones restringidas ya concedidas y aún no convertidas en acciones (dilución futura comprometida).

Su gasto ya está en la cuenta de resultados (GAAP/NIIF, valor razonable en la fecha de concesión). Lo que no recoge la
contabilidad es la dilución que llega al ejercerlas, que crece con la cotización. Datos del último 10-K (API de la SEC).
Muchas empresas desglosan sus planes por tipo de instrumento y entonces la API resumida no los trae: hay que mirar el 10-K.
"""
from __future__ import annotations

TAGS = {
    "opciones": "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber",
    "precio_ejercicio": "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingWeightedAverageExercisePrice",
    "ejercitables": "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsExercisableNumber",
    "rsu": "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber",
    "concedidas_opciones": "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsGrantsInPeriodGross",
    "concedidas_rsu": "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsGrantsInPeriod",
    "gasto_pendiente": "EmployeeServiceShareBasedCompensationNonvestedAwardsTotalCompensationCostNotYetRecognized",
}
ANNUAL = ("10-K", "10-K/A", "20-F", "20-F/A")


def _ultimo(node: dict) -> tuple[float, str] | None:
    xs = [x for v in (node or {}).get("units", {}).values() for x in v if x.get("form") in ANNUAL and x.get("end")]
    if not xs:
        return None
    x = max(xs, key=lambda x: (x["end"], x.get("filed", "")))
    return float(x["val"]), x["end"]


def opciones_vivas(facts: dict, acciones_m: float | None, precio: float | None, ultimo_cierre: str | None = None) -> dict | None:
    """Resumen con el último dato de cada concepto. `acciones_m`: acciones diluidas (millones)."""
    g = facts.get("facts", {}).get("us-gaap", {})
    out: dict = {}
    for k, tag in TAGS.items():
        v = _ultimo(g.get(tag))
        if v:
            out[k], out[f"{k}_fecha"] = v
    if not out.get("opciones") and not out.get("rsu"):
        return None
    # dato viejo (la empresa dejó de etiquetarlo): no sirve
    fechas = [out[k] for k in out if k.endswith("_fecha")]
    if ultimo_cierre and fechas and max(fechas)[:4] < str(int(ultimo_cierre[:4]) - 1):
        return None
    sh = (acciones_m or 0) * 1e6
    op, k_, rsu = out.get("opciones") or 0.0, out.get("precio_ejercicio"), out.get("rsu") or 0.0
    out["peso"] = (op + rsu) / sh if sh else None          # «overhang» bruto
    if precio and k_ is not None and op:
        itm = precio > k_
        out["in_the_money"] = itm
        # método de autocartera: acciones netas = opciones × (P − K) / P
        out["dilucion_neta"] = (op * (precio - k_) / precio) / sh if (itm and sh) else 0.0
        out["valor_intrinseco"] = op * max(precio - k_, 0.0) / 1e6   # millones
    concedidas = (out.get("concedidas_opciones") or 0) + (out.get("concedidas_rsu") or 0)
    out["burn_rate"] = concedidas / sh if (sh and concedidas) else None
    return out
