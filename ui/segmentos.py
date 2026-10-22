"""Pestaña «Segmentos»: de dónde vienen las ventas (negocio, producto y geografía) según los 10-K."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from terminal import segmentos as SG
from ui.common import cur, fig_layout, num, pct, show_cols_table

PALETTE = ["#2f6db5", "#e07b24", "#2e8b57", "#7c5cbf", "#3a9fb5", "#b0507a", "#8a8f2a", "#6b7280"]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _data(cik: int) -> pd.DataFrame:
    return SG.breakdown(cik)


def tab(T: str, ca):
    from ui.ayuda import explica
    explica("segmentos")
    eu = not int(ca.fin.cik or 0)
    seg = {}
    if eu:  # europeas: desgloses recogidos de los informes anuales y de las notas de prensa (guardados con el análisis)
        from terminal import storage
        seg = (storage.load(T) or {}).get("segmentos") or {}
        if not seg.get("anual"):
            st.info("En Europa el desglose por segmentos va en las notas del informe anual y el formato ESEF no lo etiqueta cifra a "
                    "cifra. Para esta empresa aún no lo he recogido: pídemelo y lo saco de sus informes anuales.")
            return
        df = pd.DataFrame(seg["anual"])
        st.caption(seg.get("fuente", ""))
    else:
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
    if not eu:
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
                            hovertemplate="%{y:,.0f} M" + cur() + "<extra>" + m + "</extra>")
        c1.plotly_chart(fig_layout(fig, f"Ventas por {tp.lower()}", h=340, unit=f"millones de {cur()}"), width="stretch", key=f"seg_{T}_{tp}")
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
        t.index.name = f"{tp} · ventas en millones de {cur()}"
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
    if eu:
        _eu_trimestral(T, seg)
        _eu_tiendas(T, ca, seg, df)


def _eu_trimestral(T: str, seg: dict):
    q = pd.DataFrame(seg.get("trimestral") or [])
    if q.empty:
        return
    st.markdown("## Trimestre a trimestre")
    st.caption("Ventas de cada trimestre por zona y por oficio (notas de prensa). El crecimiento es a tipos de cambio constantes, "
               "que es como lo mide la empresa: quita el efecto de la divisa.")
    for tp in [t for t in ("Geografía", "Producto o servicio") if t in set(q["Tipo"])]:
        d = q[q["Tipo"] == tp]
        periodos = list(dict.fromkeys(d.sort_values("Fin")["Periodo"]))
        v = d.pivot_table(index="Miembro", columns="Periodo", values="Valor", aggfunc="first")[periodos]
        g = d.pivot_table(index="Miembro", columns="Periodo", values="Crec_cte", aggfunc="first")
        g = g[[p for p in periodos if p in g.columns]]
        v = v.loc[v[periodos[-1]].sort_values(ascending=False).index]
        c1, c2 = st.columns(2)
        fig = go.Figure()
        for i, (m, row) in enumerate(v.iterrows()):
            fig.add_bar(x=periodos, y=list(row.values), name=m, marker_color=PALETTE[i % len(PALETTE)],
                        hovertemplate="%{x}: %{y:,.0f} M" + cur() + "<extra>" + m + "</extra>")
        fig.update_layout(barmode="stack")
        c1.plotly_chart(fig_layout(fig, f"Ventas trimestrales por {tp.lower()}", h=360, unit=f"millones de {cur()}"),
                        width="stretch", key=f"segq_{T}_{tp}")
        fig = go.Figure()
        for i, (m, row) in enumerate(g.reindex(v.index).iterrows()):
            fig.add_scatter(x=list(g.columns), y=[x * 100 if x == x and x is not None else None for x in row.values], name=m,
                            mode="lines+markers", line=dict(color=PALETTE[i % len(PALETTE)], width=2), connectgaps=False,
                            hovertemplate="%{x}: %{y:.1f} %<extra>" + m + "</extra>")
        fig.add_hline(y=0, line_color="#9ca3af", line_width=1)
        c2.plotly_chart(fig_layout(fig, f"Crecimiento a tipos constantes por {tp.lower()}", h=360, unit="% frente al mismo trimestre"),
                        width="stretch", key=f"segg_{T}_{tp}")
        t = g.reindex(v.index)
        t.index.name = f"{tp} · crecimiento a tipos constantes"
        show_cols_table(t, kinds={c: "pct" for c in t.columns})


def _eu_tiendas(T: str, ca, seg: dict, df: pd.DataFrame):
    td = seg.get("tiendas") or {}
    red = pd.DataFrame(td.get("red") or [])
    if red.empty:
        return
    st.markdown("## Tiendas")
    st.caption(td.get("fuente", ""))
    rev = {y: v for y, v in zip(ca.fin.years, ca.fin.series("revenue")) if v}
    red["Ventas"] = red["Año"].map(rev)
    red["Ventas por tienda"] = red["Ventas"] / red["Tiendas"]
    red["Ventas por tienda propia (estim.)"] = red["Ventas"] * td.get("peso_propias", 0.92) / red["Propias"]
    c = st.columns(4)
    last = red.iloc[-1]
    c[0].metric("Tiendas exclusivas", f"{int(last['Tiendas'])}", f"{int(last['Tiendas'] - red.iloc[0]['Tiendas']):+d} desde {int(red.iloc[0]['Año'])}",
                delta_color="off", delta_arrow="off")
    c[1].metric("Propias (sucursales)", f"{int(last['Propias'])}", f"{last['Propias'] / last['Tiendas']:.0%} de la red".replace(".", ","),
                delta_color="off", delta_arrow="off")
    c[2].metric("Ventas por tienda", f"{num(last['Ventas por tienda'], 1)} M{cur()}",
                f"{pct(last['Ventas por tienda'] / red.iloc[0]['Ventas por tienda'] - 1)} desde {int(red.iloc[0]['Año'])}", delta_arrow="off")
    if td.get("m2_medio_supuesto"):
        lo, hi = td["m2_medio_supuesto"]
        v = last["Ventas"] * 1e6 / last["Tiendas"]
        c[3].metric("Ventas por m² (estimación)", f"{num(v / hi / 1e3, 0)}-{num(v / lo / 1e3, 0)} mil {cur()}",
                    f"si la tienda media tiene {lo}-{hi} m²", delta_color="off", delta_arrow="off",
                    help="La empresa no publica la superficie de venta: es una estimación con una superficie media supuesta.")
    c1, c2 = st.columns(2)
    fig = go.Figure()
    fig.add_bar(x=red["Año"].astype(str), y=red["Propias"], name="Propias (sucursales)", marker_color=PALETTE[0])
    fig.add_bar(x=red["Año"].astype(str), y=red["Tiendas"] - red["Propias"], name="Concesionarios", marker_color=PALETTE[5])
    fig.update_layout(barmode="stack")
    c1.plotly_chart(fig_layout(fig, "Número de tiendas exclusivas", h=330, unit="tiendas"), width="stretch", key=f"tdn_{T}")
    fig = go.Figure(go.Scatter(x=red["Año"].astype(str), y=red["Ventas por tienda"], mode="lines+markers+text",
                               text=[num(x, 1) for x in red["Ventas por tienda"]], textposition="top center",
                               line=dict(color=PALETTE[2], width=2.5), marker=dict(size=8)))
    c2.plotly_chart(fig_layout(fig, "Ventas por tienda", h=330, unit=f"millones de {cur()} por tienda"), width="stretch", key=f"tdv_{T}")
    t = red.set_index("Año")[["Tiendas", "Propias", "Ventas", "Ventas por tienda", "Ventas por tienda propia (estim.)"]]
    t.index = t.index.astype(str)
    t = t.rename(columns={"Tiendas": "Nº tiendas", "Propias": "Nº propias", "Ventas": "Ventas (M)"})
    show_cols_table(t, kinds={"Nº tiendas": "int", "Nº propias": "int", "Ventas (M)": "m", "Ventas por tienda": "m",
                              "Ventas por tienda propia (estim.)": "m"})
    zr = pd.DataFrame(td.get("por_zona") or [])
    if not zr.empty:
        st.markdown(f"**Ventas por tienda y zona ({int(zr['Año'].max())})**")
        st.caption("Ventas de la zona entre sus tiendas. Incluye la venta online y la mayorista (perfumes, relojes) de la zona, "
                   "así que es una aproximación a la productividad de cada tienda.")
        show_cols_table(zr.set_index("Zona")[["Tiendas", "Ventas (M)", "Ventas por tienda", "Margen operativo"]],
                        kinds={"Tiendas": "int", "Ventas (M)": "m", "Ventas por tienda": "m", "Margen operativo": "pct"})
    if td.get("estrategia"):
        st.markdown("**Estrategia y objetivos de la red**")
        st.markdown("\n".join(f"- {x}" for x in td["estrategia"]).replace("$", "\\$"))
