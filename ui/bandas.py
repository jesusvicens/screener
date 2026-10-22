"""Pestaña «Bandas y sensibilidad»: ¿está cara o barata frente a sí misma? y ¿qué rentabilidad sale con cada supuesto?"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import bandas as B
from ui.common import AMBER, cur, BLUE, MUTED, NEG, POS, TEXT, fig_layout, fmt_cell, mult, num, pct, show_cols_table
from ui.historico import _clean_ratio, _daily_ratio

BAND_COL = {0.10: "#9dbbe0", 0.25: "#6f9bd1", 0.50: BLUE, 0.75: "#6f9bd1", 0.90: "#9dbbe0"}


def _band_chart(ca, ps: list, pcts: dict, label: str, unit_name: str):
    h = ca.hist.dropna()
    pts = sorted((pd.Timestamp(ca.fin.period_end[y]), v) for y, v in zip(ca.fin.years, ps) if ca.fin.period_end.get(y) and v)
    if not pts or h.empty:
        return None
    base = pd.Series({d: v for d, v in pts}).sort_index()
    step = base.reindex(h.index.union(base.index)).ffill().reindex(h.index)
    step = step[step.index >= base.index[0]].where(lambda s: s > 0)
    hh = h[h.index >= base.index[0]]
    fig = go.Figure()
    for p in (0.90, 0.75, 0.50, 0.25, 0.10):
        if p not in pcts:
            continue
        y = step * pcts[p]
        fig.add_scatter(x=y.index, y=y, name=f"{label} p{int(p * 100)} ({mult(pcts[p])})", mode="lines",
                        line=dict(color=BAND_COL[p], width=2 if p == 0.5 else 1, dash="solid" if p == 0.5 else "dot"),
                        hovertemplate="%{y:,.2f}<extra>" + f"{label} {mult(pcts[p])}" + "</extra>")
    fig.add_scatter(x=hh.index, y=hh, name="Precio", mode="lines", line=dict(color=TEXT, width=2),
                    hovertemplate="%{x|%d-%m-%Y}: %{y:,.2f}<extra>Precio</extra>")
    fig_layout(fig, "", h=380, unit=f"precio por acción frente a {unit_name} × {label} histórico")
    fig.update_layout(xaxis=dict(type="date"), hovermode="x unified")
    return fig


def _ratio_block(ca, key: str, label: str, unit_name: str, bases: dict):
    ps = B.per_share(ca.fin, key) if key != "eps" else ca.fin.series("eps_diluted")
    r = _clean_ratio(_daily_ratio(ca, ps))
    pcts = B.percentiles(r)
    if not pcts:
        st.caption(f"No hay historia suficiente para el {label}.")
        return None
    now = r.dropna().iloc[-1] if r.notna().any() else None
    P = ca.params.price
    r_hoy = (P / ps[-1]) if (P and ps and ps[-1] and ps[-1] > 0) else now
    pr = (r.dropna() <= r_hoy).mean() if r_hoy else None
    c = st.columns(6)
    c[0].metric(f"{label} hoy", mult(r_hoy), (f"percentil {pr * 100:.0f}" if pr is not None else None), delta_color="off", delta_arrow="off",
                help="Percentil: % de los días de la historia en que estuvo más barata que hoy. Bajo = barata frente a sí misma.")
    for i, p in enumerate((0.10, 0.25, 0.50, 0.75, 0.90)):
        c[i + 1].metric(f"Percentil {int(p * 100)}", mult(pcts[p]))
    rows = []
    for name, b in bases.items():
        if not b or b <= 0:
            continue
        bp = B.band_prices(pcts, b)
        rows.append({"Sobre": f"{name} ({num(b, 2)} {cur()})"} | {f"Precio a p{int(p * 100)} ({cur()})": v for p, v in bp.items()}
                    | {"Potencial a la mediana": (bp[0.5] / P - 1) if P else None})
    if rows:
        t = pd.DataFrame(rows).set_index("Sobre")
        st.markdown(f"**Precio por acción ({cur()}) si cotizara a cada percentil de su {label} histórico**")
        show_cols_table(t, height=38 + 35 * len(t), kinds={**{c: "ps" for c in t.columns}, "Potencial a la mediana": "pct"})
    fig = _band_chart(ca, ps, pcts, label, unit_name)
    if fig:
        st.plotly_chart(fig, width="stretch", key=f"band_{key}_{ca.fin.ticker}")
    return pcts


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("bandas")
    f = ca.fin
    P = ca.params.price
    norm = B.normalized_eps(f)
    st.markdown("## BPA normalizado")
    if norm:
        c = st.columns(4)
        c[0].metric("BPA último ejercicio", f'{num(norm["bpa_ultimo"], 2)} {cur()}', f"margen neto {pct(norm['margen_ultimo'])}", delta_color="off", delta_arrow="off")
        c[1].metric("BPA normalizado", f'{num(norm["bpa_normalizado"], 2)} {cur()}', f"margen medio {norm['años']} años {pct(norm['margen_medio'])}",
                    delta_color="off", delta_arrow="off",
                    help="Ventas del último año × margen neto medio de los últimos años ÷ acciones. Quita el efecto de un año excepcional.")
        c[2].metric("PER sobre el último", mult(P / norm["bpa_ultimo"]) if (P and norm["bpa_ultimo"] and norm["bpa_ultimo"] > 0) else "—")
        c[3].metric("PER normalizado", mult(P / norm["bpa_normalizado"]) if (P and norm["bpa_normalizado"] > 0) else "—")
        gap = norm["bpa_ultimo"] / norm["bpa_normalizado"] - 1 if norm["bpa_normalizado"] > 0 and norm["bpa_ultimo"] else None
        if gap is not None and abs(gap) > 0.15:
            st.caption(("⚠ El último BPA está " + ("por encima" if gap > 0 else "por debajo") + f" de lo normal ({pct(gap)}): "
                        "conviene valorar también con el normalizado."))
    else:
        st.caption("Faltan datos para normalizar el BPA.")

    eps = f.series("eps_diluted")[-1] if f.years else None
    fcfps = B.per_share(f, "fcf")[-1] if f.years else None
    st.markdown("## Bandas de PER")
    st.caption("Cuánto ha pagado el mercado por su beneficio a lo largo de los años (cada día, precio ÷ BPA del último ejercicio cerrado). "
               "El gráfico muestra qué precio tendría hoy a cada nivel habitual de PER.")
    pcts_per = _ratio_block(ca, "eps", "PER", "BPA", {"BPA último": eps, "BPA normalizado": norm.get("bpa_normalizado")})
    st.markdown("## Bandas de precio / flujo de caja libre")
    _ratio_block(ca, "fcf", "P/FCF", "FCF por acción", {"FCF por acción último": fcfps})

    st.markdown("## Sensibilidad: rentabilidad anual según crecimiento y PER de salida")
    n, r = ca.params.n, ca.params.r
    c = st.columns([1.3, 1.3, 1, 1])
    base_opts = {"BPA último": eps} | ({"BPA normalizado": norm["bpa_normalizado"]} if norm else {})
    bname = c[0].selectbox("BPA de partida", list(base_opts), key=f"sens_base_{T}")
    nn = c[1].slider("Años", 3, 15, int(n), key=f"sens_n_{T}")
    payout = 0.0
    divs, ni = f.get("dividends", f.years[-1]), f.get("net_income", f.years[-1])
    if divs and ni and ni > 0:
        payout = min(abs(divs) / ni, 1.0)
    inc_div = c[2].toggle("Con dividendos", value=payout > 0, key=f"sens_div_{T}", help=f"Payout actual {pct(payout)}")
    eps0 = base_opts[bname]
    if not (P and eps0 and eps0 > 0):
        st.info("Hace falta precio y un BPA positivo para la tabla de sensibilidad.")
        return
    med = pcts_per.get(0.5) if pcts_per else None
    mults = sorted({10, 15, 20, 25, 30} | ({round(med)} if med else set()))
    growths = [0.0, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20]
    ret, px = B.sensitivity(P, eps0, nn, growths, mults, payout if inc_div else 0.0)

    def _css(v):
        if v is None or v != v:
            return ""
        if v >= r:
            return f"color: {POS}; background-color: #eaf6ef; font-weight: 600;"
        if v < 0:
            return f"color: {NEG}; background-color: #fdeeee;"
        return f"color: {TEXT};"

    st.caption(f"Partiendo de {bname.lower()} {num(eps0, 2)} {cur()} y precio {num(P, 2)} {cur()}. Filas: crecimiento anual del BPA; columnas: PER al que "
               f"vendes dentro de {nn} años. **Verde = supera tu rentabilidad exigida ({pct(r)})**, rojo = pierdes dinero."
               + (f" La columna PER {round(med)} es la mediana histórica." if med else ""))
    sty = ret.style.format(lambda v: fmt_cell(v, "pct"), na_rep="—").map(_css)
    st.dataframe(sty, width="stretch", height=38 + 35 * len(ret))
    with st.expander(f"Precio por acción ({cur()}) dentro de {nn} años en cada caso"):
        show_cols_table(px, height=38 + 35 * len(px), kinds={c: "ps" for c in px.columns})
