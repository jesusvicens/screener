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


_md = lambda t: (t or "").replace("$", "\\$")  # noqa: E731  (que «M$» no se lea como fórmula)
PCT_FMT = lambda v: "—" if v is None or v != v else f"{v * 100:+.1f} %".replace(".", ",")  # noqa: E731


def _analisis(T: str, data: dict):
    """Análisis de comparables escrito (con cifras de los informes de cada empresa) si lo hay para esta empresa."""
    import pandas as pd
    a = data.get("comparables_analisis") or {}
    if not a:
        return
    st.markdown("## Frente a sus competidores")
    st.caption(f"Análisis con las cifras publicadas por cada empresa · actualizado el {a.get('fecha', '—')}. "
               "Abajo, la comparación automática con los datos del screener.")
    if a.get("intro"):
        st.markdown(_md(a["intro"]))
    tb = pd.DataFrame(a.get("tabla") or [])
    if not tb.empty:
        pcts = set(a.get("columnas_pct", []))
        show = tb.copy()
        for c in show.columns:
            if c in pcts:
                show[c] = [("—" if v is None or v != v else (f"{v * 100:.1f} %".replace(".", ",") if "argen" in c else PCT_FMT(v)))
                           for v in show[c]]
            elif show[c].dtype.kind in "fi":
                show[c] = [("—" if v != v else (f"{v:,.0f}".replace(",", ".") if abs(v) >= 100 else f"{v:.1f}".replace(".", ",")))
                           for v in show[c]]
        st.dataframe(show.set_index(show.columns[0]), width="stretch", height=38 + 35 * len(show))
        if a.get("nota_tabla"):
            st.caption(_md(a["nota_tabla"]))
        # gráficos: margen operativo, crecimiento del último año y del 2026, y PER
        graf = [g for g in a.get("graficos", []) if g in tb.columns]
        for i in range(0, len(graf), 2):
            cc = st.columns(2)
            for j, m in enumerate(graf[i:i + 2]):
                body = tb[[tb.columns[0], m]].dropna()
                body = body.sort_values(m)
                if body.empty:
                    continue
                is_pct = m in pcts
                lab = list(body[tb.columns[0]])
                colors = [BLUE if T.split(".")[0].upper() in str(x).upper() or str(x).startswith("Hermès") else GRAY for x in lab]
                txt = [(f"{v * 100:.1f} %".replace(".", ",") if is_pct else f"{v:.1f}x".replace(".", ",")) for v in body[m]]
                fig = go.Figure(go.Bar(x=body[m], y=lab, orientation="h", marker_color=colors, text=txt, textposition="outside",
                                       cliponaxis=False, textfont=dict(size=11), hovertemplate="%{y}: %{text}<extra></extra>"))
                if is_pct:
                    fig.update_xaxes(tickformat=".0%")
                fig.update_layout(showlegend=False, hovermode="closest")
                fig_layout(fig, m, h=60 + 30 * len(body), unit="%" if is_pct else "veces")
                fig.update_layout(yaxis=dict(type="category"), xaxis=dict(type="linear"))
                cc[j].plotly_chart(fig, width="stretch", key=f"cmpa_{T}_{m}")
    for sec in a.get("secciones", []):
        with st.expander(sec.get("titulo", ""), expanded=sec.get("abierto", False)):
            st.markdown(_md(sec.get("md", "")))
    if a.get("fuentes"):
        with st.expander("Fuentes"):
            st.markdown("\n".join(f"- [{f['titulo']}]({f['url']})" for f in a["fuentes"]))
    st.divider()
    st.markdown("## Comparación automática (datos del screener)")


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("comparables")
    try:
        _analisis(T, storage.load(T) or {})
    except Exception as e:  # noqa: BLE001
        st.caption(f"No se ha podido mostrar el análisis de comparables: {e}")
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
