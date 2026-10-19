"""Bandas de valoración (PER y P/FCF frente a su propia historia), BPA normalizado y tabla de sensibilidad."""
from __future__ import annotations

import pandas as pd

PCTS = (0.10, 0.25, 0.50, 0.75, 0.90)


def per_share(fin, key: str) -> list:
    sh = fin.series("shares_diluted")
    return [(v / s) if (v is not None and s) else None for v, s in zip(fin.series(key), sh)]


def normalized_eps(fin, years: int = 5) -> dict:
    """BPA normalizado = ventas del último año × margen neto medio de los últimos `years` años ÷ acciones diluidas.

    Quita el efecto de un año excepcional (bueno o malo) sin cambiar el tamaño actual del negocio.
    """
    rev, ni, sh = fin.series("revenue"), fin.series("net_income"), fin.series("shares_diluted")
    margins = [n / r for n, r in zip(ni, rev) if n is not None and r]
    m = margins[-years:]
    if not m or not rev or rev[-1] is None or not sh or not sh[-1]:
        return {}
    avg = sum(m) / len(m)
    eps_n = rev[-1] * avg / sh[-1]
    eps = fin.series("eps_diluted")[-1]
    return {"bpa_normalizado": eps_n, "margen_medio": avg, "años": len(m), "bpa_ultimo": eps,
            "margen_ultimo": (ni[-1] / rev[-1]) if (ni[-1] is not None and rev[-1]) else None}


def percentiles(r: pd.Series) -> dict[float, float]:
    r = r.dropna()
    if len(r) < 60:
        return {}
    return {p: float(r.quantile(p)) for p in PCTS}


def band_prices(pcts: dict[float, float], base: float | None) -> dict[float, float]:
    return {p: v * base for p, v in pcts.items()} if (base and base > 0) else {}


def sensitivity(price: float, eps0: float, n: int, growths: list[float], multiples: list[float], payout: float = 0.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rentabilidad anual y precio dentro de n años para cada combinación de crecimiento del BPA y PER de salida.

    Incluye, si hay, los dividendos (payout × BPA de cada año) sin reinvertir.
    """
    ret, px = {}, {}
    for m in multiples:
        rc, pc = [], []
        for g in growths:
            eps_n = eps0 * (1 + g) ** n
            divs = sum(eps0 * (1 + g) ** t * payout for t in range(1, n + 1))
            p_n = eps_n * m
            pc.append(p_n)
            total = p_n + divs
            rc.append((total / price) ** (1 / n) - 1 if (price and total > 0) else None)
        ret[m], px[m] = rc, pc
    idx = [f"{g:+.0%}".replace(".", ",") for g in growths]
    cols = [f"PER {m:g}".replace(".", ",") for m in multiples]
    return (pd.DataFrame(ret, index=idx).set_axis(cols, axis=1), pd.DataFrame(px, index=idx).set_axis(cols, axis=1))
