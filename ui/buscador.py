"""Buscador de empresas: americanas (SEC) y europeas (ESEF) en una sola lista.

Orden pensado para encontrar rápido: primero las de tus listas (★), después de mayor a menor capitalización,
así al escribir «app» sale Apple antes que cualquier empresa pequeña con «app» en el nombre.
Se busca por ticker o por nombre (sin distinguir mayúsculas); cada opción muestra nombre, ticker y bolsa.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from terminal import screener, sec


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _catalogo(_stamp: float) -> tuple[list[str], dict[str, str], dict[str, float]]:
    """(tickers, etiqueta por ticker, capitalización en M$ por ticker)."""
    labels: dict[str, str] = {}
    for u in sec.universe():
        t = u["ticker"].upper()
        if t not in labels:
            labels[t] = f"{u['name']} · {t} · {u.get('exchange') or '—'}"
    try:
        from terminal import esef
        for u in esef.universe():
            pais = esef.COUNTRY_NAMES.get(u.get("country", ""), u.get("country", ""))
            labels[u["ticker"].upper()] = f"{u['name']} · {u['ticker']} · {u.get('exchange') or 'Europa'} ({pais})"
    except Exception:  # noqa: BLE001
        pass
    cap: dict[str, float] = {}
    try:
        base = screener.load_base(9999)
        mk, _ = screener.load_market()
        if base is not None:
            df = screener.with_valuation(base, mk)
            cap = {str(t).upper(): float(v) for t, v in zip(df["Ticker"], pd.to_numeric(df["Capitalización (M$)"], errors="coerce"))
                   if pd.notna(v)}
    except Exception:  # noqa: BLE001
        cap = {}
    order = sorted(labels, key=lambda t: -cap.get(t, 0.0))
    return order, labels, cap


def opciones(destacadas: list[str] | None = None) -> tuple[list[str], callable]:
    """Tickers en orden de búsqueda y la función que los muestra («★ Nombre · TICKER · Bolsa»)."""
    stamp = sum(f.stat().st_mtime for f in (screener.BASE_FILE, screener.EU_BASE_FILE) if f.exists())
    order, labels, _cap = _catalogo(stamp)
    star = [t.upper() for t in (destacadas or []) if t.upper() in labels]
    s = set(star)
    tickers = star + [t for t in order if t not in s]

    def fmt(t: str) -> str:
        lab = labels.get(t, t)
        return ("★ " + lab) if t in s else lab

    return tickers, fmt


def mis_tickers() -> list[str]:
    """Empresas de tus listas (para destacarlas en el buscador)."""
    try:
        from ui.prioridad import _listas
        return sorted(_listas()["empresas"])
    except Exception:  # noqa: BLE001
        return []
