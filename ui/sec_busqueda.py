"""Buscador de texto completo en los documentos de la empresa en la SEC (dentro de la pestaña «SEC»)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import busqueda as B
from ui.common import BLUE, fig_layout, show_cols_table

EJEMPLOS = ["pricing power", "buyback", "competition", "artificial intelligence", "supply chain", "customer concentration", "goodwill impairment"]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _search(cik: int, q: str, forms: tuple[str, ...], start: str | None):
    return B.search(cik, q, list(forms), start)


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _detail(url: str, q: str):
    return B.count(url, q), B.snippets(url, q, 3)


def box(ca):
    T = ca.fin.ticker
    st.markdown("## Buscar en sus documentos")
    st.caption("Busca una palabra o frase en todos sus 10-K, 10-Q, 8-K y juntas desde 2001 (búsqueda de texto completo de la SEC). "
               "Útil para seguir un tema en el tiempo: cuántas veces lo mencionan y qué dicen. Las búsquedas van en inglés. "
               "Ejemplos: " + " · ".join(f"«{e}»" for e in EJEMPLOS) + ".")
    c = st.columns([3, 2, 1])
    q = c[0].text_input("Texto", key=f"sec_q_{T}", placeholder="p. ej. pricing power", label_visibility="collapsed")
    forms = c[1].multiselect("Tipos", list(B.FORMS), default=["10-K"], key=f"sec_f_{T}", label_visibility="collapsed",
                             placeholder="Todos los tipos")
    desde = c[2].selectbox("Desde", ["Todo", "5 años", "10 años"], key=f"sec_d_{T}", label_visibility="collapsed")
    if not q.strip():
        return
    start = None if desde == "Todo" else (pd.Timestamp.today() - pd.DateOffset(years=int(desde.split()[0]))).strftime("%Y-%m-%d")
    with st.spinner("Buscando en EDGAR…"):
        try:
            hits = _search(int(ca.fin.cik), q.strip(), tuple(B.FORMS[f] for f in forms), start)
        except Exception as e:  # noqa: BLE001
            st.error(f"La búsqueda de la SEC no ha respondido: {e}")
            return
    if not hits:
        st.info("No aparece en ningún documento con esos filtros.")
        return
    top = hits[:12]
    with st.spinner("Contando menciones y sacando fragmentos…"):
        det = [_detail(h["url"], q) for h in top]
    df = pd.DataFrame(top)
    df["Menciones"] = [d[0] for d in det]
    st.markdown(f"**{len(hits)} documentos** contienen «{q.strip()}»" + (f" (detalle de los {len(top)} más recientes)" if len(hits) > len(top) else ""))
    yearly = df[df["Tipo"].isin(["10-K", "20-F"])]
    if len(yearly) >= 2:
        y = yearly.sort_values("Fecha")
        fig = go.Figure(go.Bar(x=[str(f)[:4] for f in y["Fecha"]], y=y["Menciones"], marker_color=BLUE,
                               text=y["Menciones"], textposition="outside", cliponaxis=False,
                               hovertemplate="Informe anual %{x}: %{y} menciones<extra></extra>"))
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig_layout(fig, f"Menciones de «{q.strip()}» en cada informe anual", h=280, unit="veces"),
                        width="stretch", key=f"secq_{T}")
    show_cols_table(df[["Fecha", "Tipo", "Periodo", "Menciones", "url"]].set_index("Fecha"), height=min(38 + 35 * len(df), 460),
                    kinds={"Menciones": "int"}, column_config={"url": st.column_config.LinkColumn("Documento", display_text="abrir")})
    for h, (n, sn) in list(zip(top, det))[:6]:
        if not sn:
            continue
        with st.expander(f"{h['Tipo']} del {h['Fecha']} · {n} menciones"):
            for x in sn:
                st.markdown("> " + x.replace("$", "\\$"))
            st.markdown(f"[Abrir el documento]({h['url']})")
