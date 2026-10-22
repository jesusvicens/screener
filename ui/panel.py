"""Panel de seguimiento (tus listas y tu cartera en una pantalla) y calendario de resultados."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from terminal import calendario, storage
from ui.common import company_url, show_cols_table

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fecha(d) -> str:
    return f"{d.day} {MESES[d.month - 1]} {d.year}" if d else "—"


@st.cache_data(ttl=3600, show_spinner=False)
def _cartera_tickers() -> list[str]:
    try:
        rows = (storage.load("_CARTERA") or {}).get("movimientos", [])
        if not rows:
            return []
        from terminal import cartera as C
        pos = C.process(rows)["posiciones"]
        return sorted(pos["Ticker"].dropna().astype(str).unique()) if not pos.empty and "Ticker" in pos else []
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _histories(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Cierres diarios del último año de varias acciones en una sola descarga (Yahoo); si falla, una a una."""
    if not tickers:
        return pd.DataFrame()
    try:
        import yfinance as yf
        h = yf.download(list(tickers), period="13mo", auto_adjust=False, progress=False, threads=True)["Close"]
        if isinstance(h, pd.Series):
            h = h.to_frame(tickers[0])
        h.index = pd.to_datetime(h.index).tz_localize(None)
        if not h.dropna(how="all").empty:
            return h
    except Exception:  # noqa: BLE001
        pass
    from terminal import prices
    return pd.DataFrame({t: prices.history(t, years=2) for t in tickers})


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _next(cik: int) -> dict:
    if not cik:
        return {}  # europeas: sin calendario de la SEC
    try:
        return calendario.next_results(cik)
    except Exception:  # noqa: BLE001
        return {}


def _chg(s: pd.Series, days: int):
    s = s.dropna()
    if len(s) < 2:
        return None
    ref = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
    return (s.iloc[-1] / ref.iloc[-1] - 1) if len(ref) else None


def _seguidas(d: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for t, e in d["empresas"].items():
        out.setdefault(t, []).extend(e.get("listas") or [])
    for t in _cartera_tickers():
        out.setdefault(t, []).append("Cartera")
    return out


def panel(df: pd.DataFrame, d: dict, gu: dict):
    seg = _seguidas(d)
    if not seg:
        st.info("Cuando añadas empresas a tus listas (o tengas cartera guardada) aparecerán aquí con su precio, su evolución, "
                "la distancia a tu precio objetivo y su próximo resultado.")
        return
    filtro = st.multiselect("Listas", sorted({g for v in seg.values() for g in v}), placeholder="Todas tus listas y la cartera",
                            key="panel_listas")
    tick = [t for t, g in seg.items() if not filtro or set(g) & set(filtro)]
    idx = df.drop_duplicates("Ticker").set_index("Ticker")
    with st.spinner("Actualizando precios…"):
        h = _histories(tuple(sorted(tick)))
    rows = []
    for t in tick:
        s = h[t] if t in h else pd.Series(dtype=float)
        u = idx.loc[t] if t in idx.index else None
        price = float(s.dropna().iloc[-1]) if len(s.dropna()) else (u["Precio"] if u is not None else None)
        e = d["empresas"].get(t, {})
        obj = e.get("objetivo")
        if not obj and t in gu:  # sin objetivo: precio máximo de compra de tu análisis = valor estimado × (1 − margen exigido)
            ve, mos = (gu[t].get("resumen") or {}).get("Valor estimado"), gu[t].get("mos")
            obj = ve * (1 - (mos if mos is not None else 0.15)) if ve else None
        nx = _next(int(u["CIK"])) if u is not None and pd.notna(u.get("CIK")) else {}
        hi = s.dropna().iloc[-252:].max() if len(s.dropna()) else None
        rows.append({"Ticker": t, "Empresa": company_url(t, u["Empresa"] if u is not None else t), "Listas": ", ".join(seg[t]),
                     "Precio": price, "Var. 1 día": _chg(s, 1), "Var. 1 mes": _chg(s, 30), "Var. 1 año": _chg(s, 365),
                     "Desde máximo 52 sem.": (price / hi - 1) if (price and hi) else None,
                     "Precio objetivo": obj, "Distancia al objetivo": (price / obj - 1) if (price and obj) else None,
                     "PER": u["PER"] if u is not None else None, "Nota financiera": u["Nota financiera"] if u is not None else None,
                     "Próximos resultados": nx.get("proximo"), "Días": nx.get("dias")})
    t = pd.DataFrame(rows).set_index("Ticker")
    hits = t[(t["Distancia al objetivo"].notna()) & (t["Distancia al objetivo"] <= 0)]
    soon = t[t["Días"].notna() & (t["Días"] <= 14)].sort_values("Días")
    c = st.columns(4)
    c[0].metric("Empresas seguidas", f"{len(t)}")
    c[1].metric("En precio objetivo", f"{len(hits)}", help="Precio actual ≤ tu precio objetivo (o el precio máximo de compra de tu análisis)")
    c[2].metric("Resultados en 14 días", f"{len(soon)}")
    best = t["Var. 1 día"].dropna()
    c[3].metric("Mayor movimiento hoy", f"{best.abs().idxmax()} {best[best.abs().idxmax()] * 100:+.1f}%".replace(".", ",") if len(best) else "—")
    if len(hits):
        st.success("🔔 En tu precio objetivo: " + ", ".join(f"**{x}**" for x in hits.index))
    if len(soon):
        st.info("📅 Presentan pronto: " + ", ".join(f"**{x}** ({_fecha(r['Próximos resultados'])})" for x, r in soon.iterrows()))
    t = t.sort_values("Distancia al objetivo", na_position="last")
    t["Próximos resultados"] = [(_fecha(x) + " (est.)") if x else "—" for x in t["Próximos resultados"]]
    show_cols_table(t.drop(columns="Días"), height=min(80 + 35 * len(t), 720),
                    kinds={"Precio": "ps", "Precio objetivo": "ps", "Var. 1 día": "pct", "Var. 1 mes": "pct", "Var. 1 año": "pct",
                           "Desde máximo 52 sem.": "pct", "Distancia al objetivo": "pct", "PER": "x", "Nota financiera": "ps"},
                    column_config={"Empresa": st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$")})
    st.caption("Ordenadas por distancia a tu precio objetivo (negativa = ya por debajo). Si no has puesto objetivo, se usa el "
               "precio máximo de compra de tu análisis guardado. Precios de Yahoo con unos minutos de retraso; "
               "las fechas de resultados son estimadas por el patrón de cada empresa.")


def calendario_tab(df: pd.DataFrame, d: dict, gu: dict):
    seg = _seguidas(d)
    extra = sorted(set(gu) - set(seg))
    inc = st.toggle("Incluir también las empresas que tienes analizadas", value=True, key="cal_inc")
    tick = list(seg) + (extra if inc else [])
    if not tick:
        st.info("Añade empresas a tus listas o analízalas para ver aquí sus fechas de resultados.")
        return
    idx = df.drop_duplicates("Ticker").set_index("Ticker")
    rows = []
    bar = st.progress(0.0, "Leyendo fechas de la SEC…") if len(tick) > 8 else None
    for i, t in enumerate(tick):
        if bar:
            bar.progress((i + 1) / len(tick), f"Fechas de {t}")
        if t not in idx.index:
            continue
        u = idx.loc[t]
        nx = _next(int(u["CIK"]))
        if not nx:
            continue
        rows.append({"Ticker": t, "Empresa": company_url(t, u["Empresa"]), "Listas": ", ".join(seg.get(t, ["Analizada"])),
                     "_p": nx["proximo"], "Próximos resultados (est.)": _fecha(nx["proximo"]), "Faltan (días)": nx["dias"],
                     "Últimos resultados": _fecha(nx["ultimo"])})
    if bar:
        bar.empty()
    if not rows:
        st.caption("Sin fechas disponibles.")
        return
    t = pd.DataFrame(rows).sort_values("_p")
    # por semanas
    today = date.today()
    t["Semana"] = [("Esta semana" if (p - today).days <= 6 else ("Próxima semana" if (p - today).days <= 13 else
                    ("Este mes" if (p - today).days <= 31 else "Más adelante"))) for p in t["_p"]]
    for sem in ["Esta semana", "Próxima semana", "Este mes", "Más adelante"]:
        sub = t[t["Semana"] == sem]
        if sub.empty:
            continue
        st.markdown(f"#### {sem} · {len(sub)}")
        show_cols_table(sub.drop(columns=["_p", "Semana"]).set_index("Ticker"), height=38 + 35 * len(sub),
                        kinds={"Faltan (días)": "int"},
                        column_config={"Empresa": st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$")})
    st.caption("Fecha estimada con el calendario de años anteriores (las empresas suelen presentar en la misma semana). "
               "Confírmala en su web de inversores. Cuando presente, abre su ficha → Seguimiento → «Resultados y guías».")
