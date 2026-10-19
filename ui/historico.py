"""Pestaña «Histórico» de la ficha, con el esquema de macrotrends.

Menú de dos niveles (categoría → métrica) y, para cada métrica, el gráfico que usa macrotrends:
- cifras (ventas, beneficio, balance…): barras anuales + panel de crecimiento anual verde/rojo;
- márgenes: barras de ventas y del resultado + línea del margen;
- ratios de precio (PER, P/V, P/VC, P/FCF): cotización diaria arriba y el ratio diario abajo
  (precio de cada día / dato por acción del último ejercicio cerrado), con su media;
- precio: cotización con botones de periodo y tabla anual (media, apertura, máximo, mínimo, cierre, variación).
Debajo, la tabla anual y un resumen de crecimientos.
"""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ui.common import BLUE, GREEN, MUTED, RED, TEXT, fmt_cell, show_cols_table

AMBER_LINE = "#e07b39"

# (categoría, [(métrica, clave, tipo de dato, tipo de gráfico)])
#   tipo de dato: m (millones), ps (por acción), pct, x (múltiplo), sh (millones de acciones)
#   gráfico: flow (barras + crecimiento), level (barras sin crecimiento), margin, ratio_price, price, mcap
MENU: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    ("Precio", [("Cotización histórica", "price", "ps", "price"), ("Capitalización", "mcap", "m", "mcap")]),
    ("Ingresos y beneficio", [
        ("Ventas", "revenue", "m", "flow"), ("Beneficio bruto", "gross_profit", "m", "flow"),
        ("Resultado operativo", "operating_income", "m", "flow"), ("EBITDA", "ebitda", "m", "flow"),
        ("Beneficio neto", "net_income", "m", "flow"), ("BPA", "eps_diluted", "ps", "flow"),
        ("Acciones en circulación", "shares_diluted", "sh", "flow"),
        ("Flujo de caja operativo", "ocf", "m", "flow"), ("Flujo de caja libre", "fcf", "m", "flow")]),
    ("Activos y pasivos", [
        ("Total activo", "total_assets", "m", "flow"), ("Caja", "_cash_all", "m", "flow"),
        ("Deuda a largo plazo", "lt_debt", "m", "flow"), ("Total pasivo", "total_liabilities", "m", "flow"),
        ("Patrimonio neto", "equity", "m", "flow"), ("Valor contable por acción", "_bvps", "ps", "flow")]),
    ("Márgenes", [
        ("Todos los márgenes", "_all_margins", "pct", "all_margins"), ("Margen bruto", "gross_profit", "pct", "margin"),
        ("Margen operativo", "operating_income", "pct", "margin"), ("Margen EBITDA", "ebitda", "pct", "margin"),
        ("Margen antes de impuestos", "pretax", "pct", "margin"), ("Margen neto", "net_income", "pct", "margin"),
        ("Margen de flujo de caja libre", "fcf", "pct", "margin")]),
    ("Ratios de precio", [
        ("PER", "eps_diluted", "x", "ratio_price"), ("Precio / ventas", "_sps", "x", "ratio_price"),
        ("Precio / valor contable", "_bvps", "x", "ratio_price"), ("Precio / flujo de caja libre", "_fcfps", "x", "ratio_price")]),
    ("Otros ratios", [
        ("Liquidez corriente", "_current", "x", "level"), ("Prueba ácida", "_quick", "x", "level"),
        ("Deuda / patrimonio", "_de", "x", "level"), ("ROE", "_roe", "pct", "level"), ("ROA", "_roa", "pct", "level"),
        ("ROIC", "_roic", "pct", "level"), ("Rentabilidad s/ patrimonio tangible", "_rote", "pct", "level")]),
    ("Otras métricas", [
        ("Dividendo por acción", "_dps", "ps", "flow"), ("Rentabilidad por dividendo", "_dy", "pct", "level"),
        ("Payout", "_payout", "pct", "level"), ("Recompras", "buybacks", "m", "flow"),
        ("Remuneración en acciones", "sbc", "m", "flow"), ("I+D", "rnd", "m", "flow"),
        ("Tipo impositivo efectivo", "_tax", "pct", "level")]),
]

CSS = """
<style>
div[data-testid="stSegmentedControl"] button, div[data-testid="stButtonGroup"] button {
  border-radius: 0 !important; font-size: .86rem !important; padding: .25rem .8rem !important; }
.mt-title { font-size: 1.35rem; font-weight: 700; color: #1b2a41; margin: .4rem 0 .1rem 0; }
.mt-sub { color: #5b6573; font-size: .9rem; margin-bottom: .4rem; }
.mt-bullets li { margin-bottom: .15rem; }
</style>
"""


# ------------------------------------------------------------------ datos
def _d(a, b):
    return a / b if (a is not None and b not in (None, 0) and not (isinstance(b, float) and math.isnan(b))) else None


def series(ca, key: str) -> list:
    f, e = ca.fin, ca.eps_df
    ys = f.years
    g = f.get
    if key == "_cash_all":
        return [g("cash_sti", y) for y in ys]
    if key == "_bvps":
        return [_d(g("equity", y), g("shares_outstanding", y) or g("shares_diluted", y)) for y in ys]
    if key == "_sps":
        return [_d(g("revenue", y), g("shares_diluted", y)) for y in ys]
    if key == "_fcfps":
        return [_d(g("fcf", y), g("shares_diluted", y)) for y in ys]
    if key == "_current":
        return [_d(g("current_assets", y), g("current_liabilities", y)) for y in ys]
    if key == "_quick":
        return [_d((g("current_assets", y) or 0) - (g("inventory", y) or 0), g("current_liabilities", y))
                if g("current_assets", y) is not None else None for y in ys]
    if key == "_de":
        return [_d((g("lt_debt", y) or 0) + (g("st_debt", y) or 0), g("equity", y)) if (g("equity", y) or 0) > 0 else None for y in ys]
    if key == "_roe":
        return [_d(g("net_income", y), g("equity", y)) if (g("equity", y) or 0) > 0 else None for y in ys]
    if key == "_roa":
        return [_d(g("net_income", y), g("total_assets", y)) for y in ys]
    if key == "_roic":
        return list(ca.roic_df.loc["ROIC"]) if "ROIC" in ca.roic_df.index else [None] * len(ys)
    if key == "_rote":
        out = []
        for y in ys:
            tang = (g("equity", y) or 0) - (g("goodwill_intangibles", y) or 0)
            out.append(_d(g("net_income", y), tang) if tang > 0 else None)
        return out
    if key == "_dps":
        return list(e["Dividendo por acción"]) if "Dividendo por acción" in e else [None] * len(ys)
    if key == "_dy":
        dps = series(ca, "_dps")
        return [_d(d, ca.avg_prices.get(y)) if d else (0.0 if ca.avg_prices.get(y) else None) for d, y in zip(dps, ys)]
    if key == "_payout":
        return [_d(-(g("dividends", y) or 0), g("net_income", y)) if (g("net_income", y) or 0) > 0 else None for y in ys]
    if key == "_tax":
        return [_d(g("taxes", y), g("pretax", y)) if (g("pretax", y) or 0) > 0 else None for y in ys]
    if key == "buybacks":
        return [abs(v) if v is not None else None for v in f.series("buybacks")]
    return f.series(key)


def _growth(vals):
    out = [None]
    for a, b in zip(vals, vals[1:]):
        out.append((b / a - 1) if (a not in (None, 0) and b is not None and a > 0) else None)
    return out


def _cagr(vals, n):
    v = [x for x in vals]
    if len(v) <= n or v[-1] is None or v[-1 - n] is None or v[-1 - n] <= 0 or v[-1] <= 0:
        return None
    return (v[-1] / v[-1 - n]) ** (1 / n) - 1


def _daily_ratio(ca, per_share: list) -> pd.Series:
    """Ratio diario = precio / dato por acción del último ejercicio cerrado antes de ese día."""
    h = ca.hist
    if h is None or h.empty:
        return pd.Series(dtype=float)
    pts = sorted((pd.Timestamp(ca.fin.period_end[y]), v) for y, v in zip(ca.fin.years, per_share)
                 if ca.fin.period_end.get(y) and v is not None)
    if not pts:
        return pd.Series(dtype=float)
    base = pd.Series({d: v for d, v in pts}).sort_index()
    ps = base.reindex(h.index.union(base.index)).ffill().reindex(h.index)
    r = (h / ps).where(ps > 0)
    return r[r.index >= base.index[0]]


def _clean_ratio(r: pd.Series) -> pd.Series:
    """Quita ratios negativos y los disparados por un beneficio puntualmente minúsculo (> 4 × la mediana)."""
    v = r.where(r > 0)
    med = v.median()
    return v.where(v <= 4 * med) if pd.notna(med) and med > 0 else v


# ------------------------------------------------------------------ gráficos
def _layout(fig, h):
    fig.update_layout(template="terminal", height=h, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                      font=dict(family="Source Sans 3, Arial", size=12, color=TEXT), bargap=0.25,
                      hoverlabel=dict(bgcolor="#fff"))
    fig.update_xaxes(gridcolor="#eef0f3", linecolor="#c9ced6")
    fig.update_yaxes(gridcolor="#e3e6eb", zerolinecolor="#c9ced6")
    return fig


def _yfmt(kind):
    return {"pct": ".0%", "x": ".1f"}.get(kind, ",.2f" if kind == "ps" else ",.0f")


def _chart_flow(ys, vals, kind, label):
    gr = _growth(vals) if kind != "pct" else [None] * len(vals)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.06)
    fig.add_bar(x=ys, y=vals, marker_color=BLUE, text=[fmt_cell(v, kind) for v in vals], textposition="outside",
                textfont=dict(size=10), cliponaxis=False, hovertemplate="%{x}: %{text}<extra>" + label + "</extra>", row=1, col=1)
    fig.add_bar(x=ys, y=gr, marker_color=[GREEN if (g or 0) >= 0 else RED for g in gr],
                hovertemplate="%{x}: %{y:.1%}<extra>Crecimiento anual</extra>", row=2, col=1)
    fig.update_yaxes(tickformat=_yfmt(kind), title_text=label, title_font=dict(size=11), row=1, col=1)
    fig.update_yaxes(tickformat=".0%", title_text="Crec. anual", title_font=dict(size=11), row=2, col=1)
    fig.update_xaxes(type="category", row=2, col=1)
    fig.update_xaxes(type="category", row=1, col=1)
    return _layout(fig, 520)


def _chart_level(ys, vals, kind, label):
    fig = go.Figure()
    fig.add_bar(x=ys, y=vals, marker_color=BLUE, text=[fmt_cell(v, kind) for v in vals], textposition="outside",
                textfont=dict(size=10), cliponaxis=False, hovertemplate="%{x}: %{text}<extra>" + label + "</extra>")
    vv = [v for v in vals if v is not None]
    if vv:
        fig.add_hline(y=sum(vv) / len(vv), line_dash="dot", line_color=MUTED,
                      annotation_text=f"media {fmt_cell(sum(vv) / len(vv), kind)}", annotation_position="top left")
    fig.update_yaxes(tickformat=_yfmt(kind), title_text=label, title_font=dict(size=11))
    fig.update_xaxes(type="category")
    return _layout(fig, 440)


def _chart_margin(ca, ys, key, label):
    rev = series(ca, "revenue")
    num = series(ca, key)
    mg = [_d(n, r) for n, r in zip(num, rev)]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.55, 0.45], vertical_spacing=0.06)
    fig.add_bar(x=ys, y=rev, name="Ventas", marker_color="#9dbbe0", hovertemplate="%{x}: %{y:,.0f}<extra>Ventas</extra>", row=1, col=1)
    fig.add_bar(x=ys, y=num, name=label.replace("Margen", "").strip().capitalize() or "Resultado", marker_color=BLUE,
                hovertemplate="%{x}: %{y:,.0f}<extra></extra>", row=1, col=1)
    fig.add_scatter(x=ys, y=mg, name=label, mode="lines+markers+text", line=dict(color=AMBER_LINE, width=2.5),
                    text=[fmt_cell(m, "pct") for m in mg], textposition="top center", textfont=dict(size=10),
                    hovertemplate="%{x}: %{y:.1%}<extra>" + label + "</extra>", row=2, col=1)
    fig.update_layout(barmode="group", showlegend=True)
    fig.update_yaxes(tickformat=",.0f", title_text="Millones", title_font=dict(size=11), row=1, col=1)
    fig.update_yaxes(tickformat=".0%", title_text=label, title_font=dict(size=11), row=2, col=1)
    fig.update_xaxes(type="category")
    _layout(fig, 540)
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.04, x=0))
    return fig, mg


ALL_MARGINS = [("Margen bruto", "gross_profit"), ("Margen operativo", "operating_income"), ("Margen EBITDA", "ebitda"),
               ("Margen antes de impuestos", "pretax"), ("Margen neto", "net_income"), ("Margen FCF", "fcf")]
MCOLORS = ["#2f6db5", "#1f9e89", "#7a5cc4", "#9aa3ae", AMBER_LINE, "#2e8b57"]


def _chart_all_margins(ca, ys):
    rev = series(ca, "revenue")
    fig = go.Figure()
    data = {}
    for (lab, k), col in zip(ALL_MARGINS, MCOLORS):
        mg = [_d(n, r) for n, r in zip(series(ca, k), rev)]
        data[lab] = mg
        if any(m is not None for m in mg):
            fig.add_scatter(x=ys, y=mg, name=lab, mode="lines+markers", line=dict(color=col, width=2),
                            hovertemplate="%{x}: %{y:.1%}<extra>" + lab + "</extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(type="category")
    _layout(fig, 460)
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.08, x=0))
    return fig, data


def _range_buttons():
    return dict(buttons=[dict(count=1, label="1A", step="year", stepmode="backward"),
                         dict(count=3, label="3A", step="year", stepmode="backward"),
                         dict(count=5, label="5A", step="year", stepmode="backward"),
                         dict(count=10, label="10A", step="year", stepmode="backward"),
                         dict(step="all", label="Todo")], x=0, y=1.06, bgcolor="#f3f5f8", activecolor="#d6e2f3")


def _chart_ratio(ca, ratio: pd.Series, label):
    h = ca.hist
    if not ratio.empty:
        h = h[h.index >= ratio.index[0]]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.5, 0.5], vertical_spacing=0.05)
    fig.add_scatter(x=h.index, y=h.values, mode="lines", line=dict(color=BLUE, width=1.6),
                    hovertemplate="%{x|%d-%m-%Y}: %{y:,.2f}<extra>Precio</extra>", row=1, col=1)
    rr = ratio
    fig.add_scatter(x=rr.index, y=rr.values, mode="lines", line=dict(color=AMBER_LINE, width=1.6),
                    hovertemplate="%{x|%d-%m-%Y}: %{y:.1f}<extra>" + label + "</extra>", row=2, col=1)
    v = rr.dropna()
    if not v.empty:
        fig.add_hline(y=float(v.median()), line_dash="dot", line_color=MUTED, row=2, col=1,
                      annotation_text=f"mediana {v.median():.1f}", annotation_position="top left")
    fig.update_yaxes(title_text="Precio", title_font=dict(size=11), row=1, col=1)
    fig.update_yaxes(title_text=label, title_font=dict(size=11), row=2, col=1)
    fig.update_xaxes(rangeselector=_range_buttons(), row=1, col=1)
    return _layout(fig, 560)


def _chart_price(ca, y_series: pd.Series, label, fmt):
    fig = go.Figure()
    fig.add_scatter(x=y_series.index, y=y_series.values, mode="lines", line=dict(color=BLUE, width=1.6), fill="tozeroy",
                    fillcolor="rgba(47,109,181,.08)", hovertemplate="%{x|%d-%m-%Y}: %{y:" + fmt + "}<extra>" + label + "</extra>")
    fig.update_xaxes(rangeselector=_range_buttons())
    fig.update_yaxes(title_text=label, title_font=dict(size=11))
    return _layout(fig, 480)


# ------------------------------------------------------------------ tablas
def _annual_table(ca, vals, kind, label, with_growth=True):
    f = ca.fin
    gr = _growth(vals)
    rows = []
    for y, v, g in zip(f.years, vals, gr):
        r = {"Año fiscal": str(y), "Cierre": f.period_end.get(y, ""), label: fmt_cell(v, kind)}
        if with_growth and kind not in ("pct", "x"):
            r["Variación anual"] = fmt_cell(g, "pct") if g is not None else "—"
        rows.append(r)
    df = pd.DataFrame(rows[::-1]).set_index("Año fiscal")
    st.dataframe(df, width="stretch", height=38 + 35 * len(df))


def _summary(vals, kind, label):
    v = [x for x in vals]
    last = next((x for x in reversed(v) if x is not None), None)
    items = [f"Último ejercicio: **{fmt_cell(last, kind)}**"]
    if kind not in ("pct", "x"):
        for n in (1, 3, 5, 10):
            c = _cagr(v, n)
            if c is not None:
                items.append(f"Crecimiento anual {n} año{'s' if n > 1 else ''}: **{fmt_cell(c, 'pct')}**")
        vv = [x for x in v if x is not None]
        if len(vv) > 1:
            items.append(f"Máximo del periodo: **{fmt_cell(max(vv), kind)}** · mínimo: **{fmt_cell(min(vv), kind)}**")
    else:
        vv = [x for x in v if x is not None]
        if vv:
            items.append(f"Media del periodo: **{fmt_cell(sum(vv) / len(vv), kind)}**")
            items.append(f"Máximo: **{fmt_cell(max(vv), kind)}** · mínimo: **{fmt_cell(min(vv), kind)}**")
            last5 = vv[-5:]
            items.append(f"Media 5 años: **{fmt_cell(sum(last5) / len(last5), kind)}**")
    st.markdown("\n".join(f"- {i}" for i in items))


def _price_table(h: pd.Series):
    rows = []
    for y, s in h.groupby(h.index.year):
        rows.append({"Año": str(y), "Precio medio": s.mean(), "Apertura": s.iloc[0], "Máximo": s.max(), "Mínimo": s.min(),
                     "Cierre": s.iloc[-1]})
    df = pd.DataFrame(rows)
    df["Variación anual"] = df["Cierre"].pct_change()
    df = df.iloc[::-1].set_index("Año")
    show_cols_table(df, height=38 + 35 * len(df), kinds={c: "ps" for c in df.columns if c != "Variación anual"} | {"Variación anual": "pct"})


# ------------------------------------------------------------------ pestaña
def tab(T: str, ca, key_fn):
    st.markdown(CSS, unsafe_allow_html=True)
    f = ca.fin
    cats = [c for c, _ in MENU]
    kc, km = key_fn(T, "mt_cat"), key_fn(T, "mt_met")
    cat = st.segmented_control("Categoría", cats, default=cats[1], key=kc, label_visibility="collapsed") or cats[1]
    mets = dict(MENU)[cat]
    names = [m[0] for m in mets]
    if st.session_state.get(km) not in names:
        st.session_state[km] = names[0]
    sel = st.segmented_control("Métrica", names, key=km, label_visibility="collapsed") or names[0]
    label, key, kind, chart = next(m for m in mets if m[0] == sel)
    ys = [str(y) for y in f.years]
    name = f.name.title() if f.name.isupper() else f.name
    st.markdown(f"<div class='mt-title'>{name} · {label} {f.years[0]}-{f.years[-1]} | {f.ticker}</div>", unsafe_allow_html=True)

    if chart in ("price", "mcap"):
        h = ca.hist
        if h is None or h.empty:
            st.info("No hay cotizaciones disponibles para esta empresa.")
            return
        if chart == "price":
            st.markdown(f"<div class='mt-sub'>Cotización diaria ajustada por splits (sin dividendos). Último cierre: "
                        f"{h.iloc[-1]:,.2f} el {h.index[-1]:%d-%m-%Y}.</div>", unsafe_allow_html=True)
            st.plotly_chart(_chart_price(ca, h, "Precio", ",.2f"), width="stretch")
            st.markdown("#### Precio por año")
            _price_table(h)
        else:
            sh = series(ca, "shares_diluted")
            ratio_inv = _daily_ratio(ca, [1 / s if s else None for s in sh])  # precio / (1/acciones) = precio × acciones
            mcap = ratio_inv.dropna()
            st.markdown("<div class='mt-sub'>Capitalización diaria = cotización × acciones diluidas del último ejercicio cerrado (millones).</div>",
                        unsafe_allow_html=True)
            st.plotly_chart(_chart_price(ca, mcap, "Capitalización (M)", ",.0f"), width="stretch")
            if not mcap.empty:
                yr = mcap.groupby(mcap.index.year).last()
                df = pd.DataFrame({"Año": yr.index.astype(str), "Capitalización al cierre (M)": yr.values})
                df["Variación anual"] = df["Capitalización al cierre (M)"].pct_change()
                show_cols_table(df.iloc[::-1].set_index("Año"), height=38 + 35 * len(df),
                                kinds={"Capitalización al cierre (M)": "m", "Variación anual": "pct"})
        return

    if chart == "ratio_price":
        ps = series(ca, key)
        raw = _daily_ratio(ca, ps)
        ratio = _clean_ratio(raw)
        if ratio.dropna().empty:
            st.info("Faltan cotizaciones o el dato por acción para calcular este ratio.")
            return
        now = ratio.dropna()
        if now.empty:
            st.info("El dato por acción ha sido negativo o casi cero en todo el periodo: el ratio no tiene sentido.")
            return
        hoy = raw.dropna().iloc[-1] if not raw.dropna().empty else None
        st.markdown(f"<div class='mt-sub'>{label} = cotización de cada día / dato por acción del último ejercicio cerrado. "
                    f"Hoy: <b>{(f'{hoy:.1f}' if hoy and hoy > 0 else 'n. s.')}</b> · mediana del periodo: <b>{now.median():.1f}</b>. "
                    f"Se ocultan los valores negativos y los disparados por un beneficio puntual muy bajo (más de 4 veces la mediana).</div>",
                    unsafe_allow_html=True)
        st.plotly_chart(_chart_ratio(ca, ratio, label), width="stretch")
        c1, c2 = st.columns([3, 2])
        with c1:
            rows = []
            h = ca.hist
            for y, v in zip(f.years, ps):
                end = f.period_end.get(y)
                if not end:
                    continue
                e = pd.Timestamp(end)
                hp = h[h.index <= e]
                p = float(hp.iloc[-1]) if not hp.empty else None
                rows.append({"Cierre ejercicio": end, "Precio": p, "Dato por acción": v, label: _d(p, v) if (v or 0) > 0 else None})
            rows.append({"Cierre ejercicio": f"Hoy ({h.index[-1]:%Y-%m-%d})", "Precio": float(h.iloc[-1]), "Dato por acción": ps[-1],
                         label: _d(float(h.iloc[-1]), ps[-1]) if (ps[-1] or 0) > 0 else None})
            df = pd.DataFrame(rows[::-1]).set_index("Cierre ejercicio")
            show_cols_table(df, height=38 + 35 * len(df), kinds={"Precio": "ps", "Dato por acción": "ps", label: "x"})
        with c2:
            v = now
            st.markdown(f"- {label} actual: **{(f'{hoy:.1f}' if hoy and hoy > 0 else 'n. s.')}**\n- Mediana del periodo: **{v.median():.1f}**\n"
                        f"- Rango habitual (percentil 10-90): **{v.quantile(.1):.1f} – {v.quantile(.9):.1f}**\n"
                        f"- Mínimo: **{v.min():.1f}** · máximo: **{v.max():.1f}**")
            if hoy and hoy > 0:
                pct_rank = (v < hoy).mean()
                st.caption(f"Hoy está más caro que el {pct_rank:.0%} de los días del periodo.")
        return

    if chart == "all_margins":
        fig, data = _chart_all_margins(ca, ys)
        st.plotly_chart(fig, width="stretch")
        df = pd.DataFrame({"Año fiscal": ys[::-1], **{k: [fmt_cell(x, "pct") for x in v[::-1]] for k, v in data.items()}}).set_index("Año fiscal")
        st.dataframe(df, width="stretch", height=38 + 35 * len(df))
        return

    if chart == "margin":
        fig, mg = _chart_margin(ca, ys, key, label)
        st.plotly_chart(fig, width="stretch")
        c1, c2 = st.columns([3, 2])
        with c1:
            _annual_table(ca, mg, "pct", label, with_growth=False)
        with c2:
            _summary(mg, "pct", label)
        return

    vals = series(ca, key)
    if chart == "flow":
        st.plotly_chart(_chart_flow(ys, vals, kind, label), width="stretch")
    else:
        st.plotly_chart(_chart_level(ys, vals, kind, label), width="stretch")
    c1, c2 = st.columns([3, 2])
    with c1:
        _annual_table(ca, vals, kind, label)
    with c2:
        _summary(vals, kind, label)
        unit = {"m": f"millones de {f.currency}", "sh": "millones de acciones", "ps": "por acción"}.get(kind, "")
        st.caption(f"{label}{' en ' + unit if unit else ''}. Ejercicios fiscales (10-K en SEC EDGAR).")
