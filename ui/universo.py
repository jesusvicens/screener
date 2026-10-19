"""Tabla con todas las empresas del screener (fundamentales + precios + notas), compartida por varias pantallas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from terminal import screener


@st.cache_data(ttl=3600, show_spinner=False)
def _table(base_stamp: float, mk_stamp: float, notas_stamp: float) -> pd.DataFrame:
    base = screener.load_base(9999)
    mk, _age = screener.load_market()
    return screener.with_notas(screener.with_valuation(base, mk))


def table() -> pd.DataFrame | None:
    """Universo completo; si falta, lo baja de los datos preparados cada noche."""
    base = screener.load_base(9999)
    mk, mk_age = screener.load_market()
    if base is None or mk is None or (mk_age or 0) > 30:
        try:
            screener.sync_from_repo()
        except Exception:  # noqa: BLE001
            pass
        base = screener.load_base(9999)
    if base is None:
        return None
    stamp = lambda p: p.stat().st_mtime if p.exists() else 0.0  # noqa: E731
    return _table(stamp(screener.BASE_FILE), stamp(screener.PRICES_FILE), stamp(screener.NOTAS_FILE))
