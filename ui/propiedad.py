"""Pestaña «Directivos y fondos»: compras/ventas de directivos (formulario 4) y superinversores que la tienen (13F)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import insiders as I
from terminal import superinversores as S
from ui.common import NEG, POS, TEXT, fig_layout, money, num, pct, show_cols_table

CAMBIO_ICON = {"Nueva": "🆕 Nueva", "Sube": "▲ Sube", "Baja": "▼ Baja", "Igual": "＝ Igual", "Vendida": "✕ Vendida"}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _tx(cik: int) -> pd.DataFrame:
    return I.transactions(cik)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _si():
    return S.load()


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("propiedad")
    st.markdown("## Directivos y consejeros (formulario 4)")
    with st.spinner("Leyendo los formularios 4 de la SEC (la primera vez tarda unos segundos)…"):
        try:
            df = _tx(int(ca.fin.cik))
        except Exception as e:  # noqa: BLE001
            df = pd.DataFrame()
            st.warning(f"No he podido leer los formularios 4: {e}")
    if df.empty:
        st.caption("Sin operaciones de directivos en los últimos dos años.")
    else:
        s = I.summary(df, 12)
        c = st.columns(4)
        c[0].metric("Compras en mercado (12 m)", f"{s['compras']}", f"{s['compradores']} personas · {money(s['importe_compras'] / 1e6)}",
                    delta_color="normal" if s["compras"] else "off", delta_arrow="off",
                    help="Compras con su propio dinero (código P). Es la señal que importa.")
        c[1].metric("Ventas en mercado (12 m)", f"{s['ventas']}", f"{s['vendedores']} personas · {money(s['importe_ventas'] / 1e6)}",
                    delta_color="off", delta_arrow="off",
                    help="Ventas (código S). Suelen ser por impuestos, diversificación o planes programados: pesan poco.")
        c[2].metric("Ventas con plan 10b5-1", f"{s['ventas_plan']}", help="Programadas de antemano: no reflejan una opinión del momento.")
        last_buy = df[df["Código"] == "P"]["Fecha"].max()
        c[3].metric("Última compra", last_buy.strftime("%d/%m/%Y") if pd.notna(last_buy) else "—")
        if s["compras"] and s["compradores"] >= 2:
            st.markdown(f"<span class='pill ok'>✓ Compras de {s['compradores']} directivos distintos en el último año</span>", unsafe_allow_html=True)

        h = ca.hist.dropna()
        h = h[h.index >= pd.Timestamp.today() - pd.DateOffset(years=2)]
        mk = df[df["Código"].isin(["P", "S"])].copy()
        if not h.empty and not mk.empty:
            fig = go.Figure()
            fig.add_scatter(x=h.index, y=h, mode="lines", name="Precio", line=dict(color=TEXT, width=1.5),
                            hovertemplate="%{x|%d-%m-%Y}: %{y:,.2f}<extra>Precio</extra>")
            for code, name, color, sym in [("P", "Compra de directivo", POS, "triangle-up"), ("S", "Venta de directivo", NEG, "triangle-down")]:
                d = mk[mk["Código"] == code].groupby(["Fecha", "Quién"], as_index=False).agg(Importe=("Importe", "sum"), Precio=("Precio", "mean"))
                if d.empty:
                    continue
                size = (d["Importe"].abs() / max(d["Importe"].abs().max(), 1) * 14 + 8).clip(8, 22)
                fig.add_scatter(x=d["Fecha"], y=d["Precio"], mode="markers", name=name,
                                marker=dict(color=color, size=size, symbol=sym, line=dict(color="#fff", width=1)),
                                text=[f"{q}: {money(abs(i) / 1e6)}" for q, i in zip(d["Quién"], d["Importe"])],
                                hovertemplate="%{x|%d-%m-%Y} · %{text}<extra></extra>")
            fig_layout(fig, "Precio y operaciones de directivos (2 años)", h=340, unit="tamaño = importe")
            fig.update_layout(xaxis=dict(type="date"), hovermode="closest")
            st.plotly_chart(fig, width="stretch", key=f"ins_{T}")

        only = st.toggle("Solo compras y ventas en mercado", value=True, key=f"ins_only_{T}",
                         help="Oculta concesiones, ejercicios de opciones y retenciones por impuestos")
        t = df[df["Código"].isin(["P", "S"])] if only else df
        t = t.head(200).copy()
        t["Fecha"] = t["Fecha"].dt.strftime("%d/%m/%Y")
        t["Plan 10b5-1"] = t["Plan 10b5-1"].map({True: "Sí", False: ""})
        show_cols_table(t[["Fecha", "Quién", "Cargo", "Operación", "Acciones", "Precio", "Importe", "Tras la operación", "Plan 10b5-1", "url"]],
                        height=min(38 + 35 * len(t), 460),
                        kinds={"Acciones": "m", "Precio": "ps", "Importe": "m", "Tras la operación": "m"},
                        column_config={"url": st.column_config.LinkColumn("Documento", display_text="ver")})

    st.markdown("## Superinversores que la tienen (13F)")
    si = _si()
    if si is None or si.empty:
        st.info("Las carteras 13F se preparan cada semana por la noche. Si quieres, calcúlalas ahora (≈1 minuto).")
        if st.button("Calcular carteras 13F ahora", key="si_build"):
            bar = st.progress(0.0)
            df_si = S.build(lambda p, m: bar.progress(p, m))
            S.save(df_si)
            _si.clear()
            st.rerun()
        return
    q = si["trimestre"].max()
    st.caption(f"{si['fondo'].nunique()} fondos seguidos · carteras a cierre de {pd.Timestamp(q):%d/%m/%Y} (los 13F se publican hasta 45 días después). "
               "Peso = % de la cartera declarada del fondo.")
    h = S.holders(si, ca.fin.name)
    if h.empty:
        st.caption("Ninguno de los fondos seguidos la tiene en su última cartera.")
    else:
        act = h[h["Cambio"] != "Vendida"]
        c = st.columns(3)
        c[0].metric("Fondos que la tienen", f"{act['fondo'].nunique()}")
        c[1].metric("La compran o suben", f"{h[h['Cambio'].isin(['Nueva', 'Sube'])]['fondo'].nunique()}")
        c[2].metric("La reducen o venden", f"{h[h['Cambio'].isin(['Baja', 'Vendida'])]['fondo'].nunique()}")
        t = h.assign(Cambio=h["Cambio"].map(CAMBIO_ICON))[["fondo", "gestor", "emisor", "peso", "valor", "acciones", "Cambio", "Var. acciones", "trimestre"]]
        t = t.rename(columns={"fondo": "Fondo", "gestor": "Gestor", "emisor": "Título", "peso": "Peso en cartera", "valor": "Valor ($)",
                              "acciones": "Acciones", "trimestre": "Trimestre"})
        t["Valor ($)"] = t["Valor ($)"] / 1e6
        t = t.rename(columns={"Valor ($)": "Valor (M$)"})
        show_cols_table(t.set_index("Fondo"), height=38 + 35 * len(t),
                        kinds={"Peso en cartera": "pct", "Valor (M$)": "m", "Acciones": "m", "Var. acciones": "pct"})
    with st.expander("Fondos seguidos"):
        st.markdown(" · ".join(f"**{k}** ({v[1]})" for k, v in S.FUNDS.items()))
