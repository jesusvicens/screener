"""Precios de cotización (gratis): Yahoo Finance vía yfinance y, si falla, Stooq.

Si ninguna fuente responde, la terminal te deja escribir el precio a mano.
"""
from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
import requests


def history(ticker: str, years: int = 12) -> pd.Series:
    """Serie diaria de cierres ajustados (por splits). Vacía si no hay datos."""
    t = ticker.upper().replace(".", "-")
    try:  # ficha guardada anoche en tu repo privado (empresas analizadas, en listas o en cartera)
        from . import remoto
        s = remoto.ficha_prices(t)
        if s is not None and (pd.Timestamp(date.today()) - s.index[-1]).days <= 5:
            return s[s.index >= pd.Timestamp(date.today() - timedelta(days=365 * years))]
    except Exception:  # noqa: BLE001
        pass
    try:
        import yfinance as yf
        h = yf.Ticker(t).history(period=f"{years}y", auto_adjust=False)
        if h is not None and not h.empty:
            s = h["Close"].copy()
            s.index = pd.to_datetime(s.index).tz_localize(None)
            return s.dropna()
    except Exception:
        pass
    try:
        url = f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d"
        r = requests.get(url, timeout=20)
        if r.ok and r.text.startswith("Date"):
            df = pd.read_csv(io.StringIO(r.text), parse_dates=["Date"]).set_index("Date")
            s = df["Close"].dropna()
            return s[s.index >= pd.Timestamp(date.today() - timedelta(days=365 * years))]
    except Exception:
        pass
    return pd.Series(dtype=float)


def last_price(hist: pd.Series) -> tuple[float | None, str | None]:
    if hist is None or hist.empty:
        return None, None
    return float(hist.iloc[-1]), hist.index[-1].strftime("%d-%m-%Y")


def fiscal_year_average(hist: pd.Series, period_end: dict[int, str]) -> dict[int, float]:
    """Precio medio de cada ejercicio fiscal (lo que usa tu hoja «Modelo EPS» para el PER histórico)."""
    out: dict[int, float] = {}
    if hist is None or hist.empty:
        return out
    for fy, end in period_end.items():
        if not end:
            continue
        e = pd.Timestamp(end)
        s = hist[(hist.index > e - pd.Timedelta(days=365)) & (hist.index <= e)]
        if len(s) > 150:
            out[fy] = float(s.mean())
    return out


def batch_last_prices(tickers: list[str]) -> dict[str, float]:
    """Último precio para muchos tickers a la vez (para el screener)."""
    out: dict[str, float] = {}
    if not tickers:
        return out
    try:
        import yfinance as yf
        tk = [t.upper().replace(".", "-") for t in tickers]
        for i in range(0, len(tk), 200):
            chunk = tk[i:i + 200]
            df = yf.download(chunk, period="5d", progress=False, auto_adjust=False, threads=True, group_by="column")
            if df is None or df.empty:
                continue
            close = df["Close"] if "Close" in df else df
            if isinstance(close, pd.Series):
                close = close.to_frame(chunk[0])
            last = close.ffill().iloc[-1]
            for t, v in last.items():
                if pd.notna(v):
                    out[str(t)] = float(v)
    except Exception:
        pass
    return out
