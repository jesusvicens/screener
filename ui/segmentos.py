"""Pestaña «Segmentos»: de dónde vienen las ventas (negocio, producto y geografía) según los 10-K."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import segmentos as SG
from ui.common import fig_layout

PALETTE = ["#2f6db5", "#e07b24", "#2e8b57", "#7c5cbf", "#3a9fb5", "#b0507a", "#8a8f2a", "#6b7280"]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _data(cik: int) -> pd.DataFrame:
    return SG.breakdown(cik)


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("segmentos")
    with st.spinner("Leyendo los desgloses de los últimos 10-K…"):
        try:
            df = _data(int(ca.fin.cik))
        except Exception as e:  # noqa: BLE001
            st.warning(f"No he podido leer los desgloses: {e}")
            return
    if df is None or df.empty:
        st.info("Esta empresa no publica desgloses por segmento, producto o geografía en el XBRL de sus 10-K (o solo tiene un segmento).")
        return
    rev = {y: v for y, v in zip(ca.fin.years, ca.fin.series("revenue")) if v}
    tipos = [t for t in ("Segmento", "Producto o servicio", "Geografía") if t in set(df["Tipo"])]
    st.caption("Datos de los 10-K (cada uno trae tres años). Los nombres son los que usa la empresa; si reorganiza sus segmentos, "
               "los años antiguos pueden no ser comparables. En geografía, algunas empresas dan a la vez una región y un país "
               "dentro de ella (p. ej. «Américas» y «Estados Unidos»): no siempre suman el total.")
    for tp in tipos:
        p = SG.pivot(df, tp, "Ventas")
        if p.empty:
            continue
        st.markdown(f"## Ventas por {tp.lower()}")
        p = p.head(8)
        years = [str(c) for c in p.columns]
        c1, c2 = st.columns([1.4, 1])
        fig = go.Figure()
        for i, (m, row) in enumerate(p.iterrows()):
            fig.add_scatter(x=years, y=list(row.values), name=m, mode="lines+markers",
                            line=dict(color=PALETTE[i % len(PALETTE)], width=2), marker=dict(size=8),
                            hovertemplate="%{y:,.0f} M$<extra>" + m + "</extra>")
        c1.plotly_chart(fig_layout(fig, f"Ventas por {tp.lower()}", h=340, unit="millones de $"), width="stretch", key=f"seg_{T}_{tp}")
        last = p.columns[-1]
        tot = rev.get(int(last)) or p[last].clip(lower=0).sum()
        share = (p[last] / tot).dropna()
        fig = go.Figure(go.Bar(x=share.values, y=list(share.index), orientation="h",
                               marker_color=[PALETTE[list(p.index).index(m) % len(PALETTE)] for m in share.index],
                               text=[f"{v:.0%}" for v in share.values], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: %{x:.1%}<extra></extra>"))
        fig.update_layout(showlegend=False, hovermode="closest")
        fig_layout(fig, f"Peso en las ventas de {last}", h=340, unit="% del total")
        fig.update_layout(xaxis=dict(type="linear", tickformat=".0%"), yaxis=dict(type="category", autorange="reversed"))
        c2.plotly_chart(fig, width="stretch", key=f"segw_{T}_{tp}")
        t = p.copy()
        t.columns = [str(c) for c in t.columns]
        g = p.pct_change(axis=1, fill_method=None).iloc[:, -1]
        cagr = None
        if p.shape[1] >= 4:
            cagr = (p.iloc[:, -1] / p.iloc[:, -4]) ** (1 / 3) - 1
        t[f"Crec. {last}"] = g.values
        if cagr is not None:
            t["CAGR 3 años"] = cagr.where(p.iloc[:, -4] > 0).values
        t[f"Peso {last}"] = (p[last] / tot).values
        st.dataframe(t.style.format(lambda v: "—" if v != v or v is None else f"{v:,.0f}".replace(",", "."), subset=years, na_rep="—")
                     .format(lambda v: "—" if v != v or v is None else f"{v * 100:.1f}%".replace(".", ","),
                             subset=[c for c in t.columns if c not in years], na_rep="—")
                     .map(lambda v: "" if v != v or v is None else ("color:#1e7b4a" if v > 0 else "color:#b42318"),
                          subset=[c for c in t.columns if c.startswith(("Crec", "CAGR"))]),
                     width="stretch", height=38 + 35 * len(t))
        op = SG.pivot(df, tp, "Resultado operativo")
        if not op.empty:
            common = [c for c in op.columns if c in p.columns]
            mg = (op[common] / p.loc[op.index.intersection(p.index), common]).dropna(how="all")
            if not mg.empty:
                st.markdown(f"**Margen operativo por {tp.lower()}**")
                mg.columns = [str(c) for c in mg.columns]
                st.dataframe(mg.style.format(lambda v: "—" if v != v else f"{v * 100:.1f}%".replace(".", ","), na_rep="—"),
                             width="stretch", height=38 + 35 * len(mg))
