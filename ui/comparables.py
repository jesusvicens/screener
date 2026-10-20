"""Pestaña «Comparables» de la ficha: tu empresa al lado de sus competidores."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from terminal import comparables as C
from terminal import storage
from ui import universo
from ui.common import BLUE, MUTED, company_url, fig_layout, fmt_cell, show_cols_table

GRAY = "#b8c2cf"
CHARTS = [("Margen operativo", "pct"), ("ROIC", "pct"), ("CAGR ventas 5a", "pct"), ("CAGR BPA 5a", "pct"),
          ("PER", "x"), ("P/FCF", "x"), ("Margen FCF", "pct"), ("Nota financiera", "ps")]


def _save(T: str, peers: list[str]):
    data = storage.load(T) or {}
    data["comparables"] = peers
    try:
        storage.save(T, data)
        st.toast("Comparables guardados")
    except Exception as e:  # noqa: BLE001
        st.error(f"No se han podido guardar: {e}")


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("comparables")
    df = universo.table()
    if df is None:
        st.info("Faltan los datos del screener (se preparan cada noche). Abre el Screener una vez y vuelve aquí.")
        return
    if T not in set(df["Ticker"]):
        st.info(f"{T} no está en el universo del screener (p. ej. emisor extranjero sin datos anuales en la SEC).")
        return
    k = f"peers_{T}"
    saved = (storage.load(T) or {}).get("comparables")
    if k not in st.session_state:
        st.session_state[k] = saved or C.suggest(df, T)
    me = df[df["Ticker"] == T].iloc[0]
    st.caption(f"Industria: **{me.get('Industria', '—')}** · sector: {me.get('Sector', '—')}. "
               + ("Comparables guardados por ti." if saved else "Propuesta automática: misma industria y ventas parecidas. Cámbialos y guarda."))
    opts = sorted(set(df["Ticker"]))
    c = st.columns([5, 1, 1])
    peers = c[0].multiselect("Comparables", opts, key=k, max_selections=12, label_visibility="collapsed",
                             placeholder="Añade tickers para comparar…")
    if c[1].button("Guardar", key=f"peers_save_{T}", width="stretch", type="primary"):
        _save(T, peers)
    if c[2].button("Propuesta", key=f"peers_auto_{T}", width="stretch", help="Vuelve a la propuesta automática"):
        st.session_state.pop(k, None)
        st.session_state[k] = C.suggest(df, T)
        st.rerun()
    if not peers:
        st.info("Añade al menos un comparable.")
        return
    tb = C.table(df, T, peers)
    pos = C.position(tb, T)

    # Resumen: dónde queda frente al grupo
    best = [m for m, (r, n) in pos.items() if r == 1]
    worst = [m for m, (r, n) in pos.items() if r == n]
    st.markdown("## Dónde queda frente a sus comparables")
    cols = st.columns(4)
    for i, (m, kind) in enumerate([("Margen operativo", "pct"), ("ROIC", "pct"), ("CAGR ventas 5a", "pct"), ("PER", "x")]):
        if m not in tb:
            continue
        v, med = tb.loc[T, m], tb.loc["Mediana", m] if "Mediana" in tb.index else None
        r = pos.get(m)
        cols[i].metric(m, fmt_cell(v, kind), (f"{r[0]}.º de {r[1]} · mediana {fmt_cell(med, kind)}" if r else None),
                       delta_color="off", delta_arrow="off")
    if best:
        st.markdown(f"<span class='pill ok'>✓ La mejor del grupo en</span> {', '.join(best)}", unsafe_allow_html=True)
    if worst:
        st.markdown(f"<span class='pill ko'>✗ La peor del grupo en</span> {', '.join(worst)}", unsafe_allow_html=True)

    st.markdown("## Tabla comparativa")
    out = tb.copy()
    out["Empresa"] = [company_url(t, n) if t != "Mediana" else "" for t, n in zip(out.index, out["Empresa"])]
    show_cols_table(out, height=38 + 35 * len(out), column_config={
        "Empresa": st.column_config.LinkColumn("Empresa", display_text=r"#(.*)$", help="Abre la ficha en otra pestaña")})
    st.caption("La última fila es la mediana de los comparables (sin tu empresa). Clic en el nombre para abrir su ficha.")

    st.markdown("## Gráficos")
    st.caption("Tu empresa en azul; la línea discontinua es la mediana de los comparables.")
    for row in range(0, len(CHARTS), 2):
        cc = st.columns(2)
        for j, (m, kind) in enumerate(CHARTS[row:row + 2]):
            if m not in tb:
                continue
            body = tb.drop(index="Mediana", errors="ignore")[[m]].dropna()
            if kind == "x":
                body = body[body[m] > 0]
            body = body.sort_values(m)
            if body.empty:
                continue
            colors = [BLUE if t == T else GRAY for t in body.index]
            fig = go.Figure(go.Bar(x=body[m], y=list(body.index), orientation="h", marker_color=colors,
                                   text=[fmt_cell(v, kind) for v in body[m]], textposition="outside", cliponaxis=False,
                                   textfont=dict(size=11), hovertemplate="%{y}: %{text}<extra></extra>"))
            med = tb.loc["Mediana", m] if "Mediana" in tb.index else None
            if med is not None and med == med:
                fig.add_vline(x=med, line_dash="dash", line_color=MUTED, line_width=1)
            if kind == "pct":
                fig.update_xaxes(tickformat=".0%")
            fig.update_layout(showlegend=False, hovermode="closest")
            fig_layout(fig, m, h=60 + 34 * len(body), unit={"pct": "%", "x": "veces", "ps": "nota de 0 a 10"}.get(kind, ""))
            fig.update_layout(yaxis=dict(type="category"), xaxis=dict(type="linear"))
            cc[j].plotly_chart(fig, width="stretch", key=f"cmp_{T}_{m}")
